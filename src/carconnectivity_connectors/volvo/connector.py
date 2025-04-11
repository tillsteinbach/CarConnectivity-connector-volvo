"""Module implements the connector to interact with the Volvo API."""
from __future__ import annotations
from typing import TYPE_CHECKING

import threading

import json
import os
import traceback
import logging
import netrc
from datetime import datetime, timezone, timedelta
import requests

from carconnectivity.garage import Garage
from carconnectivity.errors import AuthenticationError, TooManyRequestsError, RetrievalError, APIError, APICompatibilityError, \
    TemporaryAuthenticationError, SetterError, CommandError
from carconnectivity.util import robust_time_parse, log_extra_keys, config_remove_credentials
from carconnectivity.units import Length, Power, Speed
from carconnectivity.vehicle import GenericVehicle
from carconnectivity.doors import Doors
from carconnectivity.windows import Windows
from carconnectivity.lights import Lights
from carconnectivity.drive import GenericDrive, ElectricDrive, CombustionDrive
from carconnectivity.battery import Battery
from carconnectivity.attributes import BooleanAttribute, DurationAttribute, GenericAttribute, TemperatureAttribute, EnumAttribute, LevelAttribute, \
    CurrentAttribute
from carconnectivity.units import Temperature
from carconnectivity.command_impl import ClimatizationStartStopCommand, WakeSleepCommand, HonkAndFlashCommand, LockUnlockCommand, ChargingStartStopCommand, \
    WindowHeatingStartStopCommand
from carconnectivity.climatization import Climatization
from carconnectivity.commands import Commands
from carconnectivity.charging import Charging
from carconnectivity.charging_connector import ChargingConnector
from carconnectivity.position import Position
from carconnectivity.enums import ConnectionState
from carconnectivity.window_heating import WindowHeatings

from carconnectivity_connectors.base.connector import BaseConnector
from carconnectivity_connectors.volvo.auth.session_manager import SessionManager, SessionToken, Service
from carconnectivity_connectors.volvo.auth.volvo_session import VolvoSession

from carconnectivity_connectors.volvo.vehicle import VolvoVehicle, VolvoElectricVehicle, VolvoCombustionVehicle, VolvoHybridVehicle

from carconnectivity_connectors.volkswagen._version import __version__

SUPPORT_IMAGES = False
try:
    from PIL import Image
    import base64
    import io
    SUPPORT_IMAGES = True
    from carconnectivity.attributes import ImageAttribute
except ImportError:
    pass

if TYPE_CHECKING:
    from typing import Dict, List, Optional, Any, Union

    from carconnectivity.carconnectivity import CarConnectivity

LOG: logging.Logger = logging.getLogger("carconnectivity.connectors.volvo")
LOG_API: logging.Logger = logging.getLogger("carconnectivity.connectors.volvo-api-debug")


# pylint: disable=too-many-lines
class Connector(BaseConnector):
    """
    Connector class for Volvo API connectivity.
    Args:
        car_connectivity (CarConnectivity): An instance of CarConnectivity.
        config (Dict): Configuration dictionary containing connection details.
    Attributes:
        max_age (Optional[int]): Maximum age for cached data in seconds.
    """
    def __init__(self, connector_id: str, car_connectivity: CarConnectivity, config: Dict) -> None:
        BaseConnector.__init__(self, connector_id=connector_id, car_connectivity=car_connectivity, config=config, log=LOG, api_log=LOG_API)

        self._background_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self.connection_state: EnumAttribute = EnumAttribute(name="connection_state", parent=self, value_type=ConnectionState,
                                                             value=ConnectionState.DISCONNECTED, tags={'connector_custom'})
        self.interval: DurationAttribute = DurationAttribute(name="interval", parent=self, tags={'connector_custom'})
        self.interval.minimum = timedelta(seconds=60)
        self.interval._is_changeable = True  # pylint: disable=protected-access

        self.commands: Commands = Commands(parent=self)

        LOG.info("Loading volvo connector with config %s", config_remove_credentials(config))

        if 'vcc_api_key_primary' in config and config['vcc_api_key_primary'] is not None:
            self.active_config['vcc_api_key_primary'] = config['vcc_api_key_primary']
        else:
            raise AuthenticationError('vcc_api_key_primary was not found in config')

        if 'vcc_api_key_secondary' in config and config['vcc_api_key_secondary'] is not None:
            self.active_config['vcc_api_key_secondary'] = config['vcc_api_key_secondary']
        else:
            raise AuthenticationError('vcc_api_key_secondary was not found in config')
        
        if 'connected_vehicle_token' in config and config['connected_vehicle_token'] is not None:
            self.active_config['connected_vehicle_token'] = config['connected_vehicle_token']
        else:
            raise AuthenticationError('connected_vehicle_token was not found in config')

        if 'location_token' in config and config['location_token'] is not None:
            self.active_config['location_token'] = config['location_token']
        else:
            self.active_config['location_token'] = None

        self.active_config['interval'] = 180
        if 'interval' in config:
            self.active_config['interval'] = config['interval']
            if self.active_config['interval'] < 60:
                raise ValueError('Intervall must be at least 60 seconds')
        self.active_config['max_age'] = self.active_config['interval'] - 1
        if 'max_age' in config:
            self.active_config['max_age'] = config['max_age']
        self.interval._set_value(timedelta(seconds=self.active_config['interval']))  # pylint: disable=protected-access

        self._manager: SessionManager = SessionManager(tokenstore=car_connectivity.get_tokenstore(), cache=car_connectivity.get_cache())
        connected_vehicle_session: requests.Session = self._manager.get_session(Service.VOLVO_CONNECTED_VEHICLE, SessionToken(
                vcc_api_key_primary=self.active_config['vcc_api_key_primary'],
                vcc_api_key_secondary=self.active_config['vcc_api_key_secondary'],
                access_token=self.active_config['connected_vehicle_token']))
        if not isinstance(connected_vehicle_session, VolvoSession):
            raise AuthenticationError('Could not create session')
        self.connected_vehicle_session: VolvoSession = connected_vehicle_session
        self.connected_vehicle_session.retries = 3
        self.connected_vehicle_session.timeout = 180

        if self.active_config['location_token'] is not None:
            location_session: requests.Session = self._manager.get_session(Service.VOLVO_LOCATION, SessionToken(
                    vcc_api_key_primary=self.active_config['vcc_api_key_primary'],
                    vcc_api_key_secondary=self.active_config['vcc_api_key_secondary'],
                    access_token=self.active_config['location_token']))
            if not isinstance(connected_vehicle_session, VolvoSession):
                raise AuthenticationError('Could not create session')
            self.location_session: Optional[VolvoSession] = location_session
            self.location_session.retries = 3
            self.location_session.timeout = 180
        else:
            self.location_session = None

        self._elapsed: List[timedelta] = []

    def startup(self) -> None:
        self._background_thread = threading.Thread(target=self._background_loop, daemon=False)
        self._background_thread.name = 'carconnectivity.connectors.volvo-background'
        self._background_thread.start()
        self.healthy._set_value(value=True)  # pylint: disable=protected-access

    def _background_loop(self) -> None:
        self._stop_event.clear()
        fetch: bool = True
        self.connection_state._set_value(value=ConnectionState.CONNECTING)  # pylint: disable=protected-access
        while not self._stop_event.is_set():
            interval = 300
            try:
                try:
                    if fetch:
                        self.fetch_all()
                        fetch = False
                    else:
                        self.update_vehicles()
                    self.last_update._set_value(value=datetime.now(tz=timezone.utc))  # pylint: disable=protected-access
                    if self.interval.value is not None:
                        interval: float = self.interval.value.total_seconds()
                except Exception:
                    self.connection_state._set_value(value=ConnectionState.ERROR)  # pylint: disable=protected-access
                    if self.interval.value is not None:
                        interval: float = self.interval.value.total_seconds()
                    raise
            except TooManyRequestsError as err:
                LOG.error('Retrieval error during update. Too many requests from your account (%s). Will try again after 15 minutes', str(err))
                self.connection_state._set_value(value=ConnectionState.ERROR)  # pylint: disable=protected-access
                self._stop_event.wait(900)
            except RetrievalError as err:
                LOG.error('Retrieval error during update (%s). Will try again after configured interval of %ss', str(err), interval)
                self.connection_state._set_value(value=ConnectionState.ERROR)  # pylint: disable=protected-access
                self._stop_event.wait(interval)
            except APICompatibilityError as err:
                LOG.error('API compatability error during update (%s). Will try again after configured interval of %ss', str(err), interval)
                self.connection_state._set_value(value=ConnectionState.ERROR)  # pylint: disable=protected-access
                self._stop_event.wait(interval)
            except TemporaryAuthenticationError as err:
                LOG.error('Temporary authentification error during update (%s). Will try again after configured interval of %ss', str(err), interval)
                self.connection_state._set_value(value=ConnectionState.ERROR)  # pylint: disable=protected-access
                self._stop_event.wait(interval)
            except Exception as err:
                LOG.critical('Critical error during update: %s', traceback.format_exc())
                self.healthy._set_value(value=False)  # pylint: disable=protected-access
                self.connection_state._set_value(value=ConnectionState.ERROR)  # pylint: disable=protected-access
                raise err
            else:
                self.connection_state._set_value(value=ConnectionState.CONNECTED)  # pylint: disable=protected-access
                self._stop_event.wait(interval)
        # When leaving the loop, set the connection state to disconnected
        self.connection_state._set_value(value=ConnectionState.DISCONNECTED)  # pylint: disable=protected-access

    def persist(self) -> None:
        """
        Persists the current state using the manager's persist method.

        This method calls the `persist` method of the `_manager` attribute to save the current state.
        """
        self._manager.persist()

    def shutdown(self) -> None:
        """
        Shuts down the connector by persisting current state, closing the session,
        and cleaning up resources.

        This method performs the following actions:
        1. Persists the current state.
        2. Closes the session.
        3. Sets the session and manager to None.
        4. Calls the shutdown method of the base connector.

        Returns:
            None
        """
        # Disable and remove all vehicles managed soley by this connector
        for vehicle in self.car_connectivity.garage.list_vehicles():
            if len(vehicle.managing_connectors) == 1 and self in vehicle.managing_connectors:
                self.car_connectivity.garage.remove_vehicle(vehicle.id)
                vehicle.enabled = False
        self._stop_event.set()
        self.connected_vehicle_session.close()
        if self._background_thread is not None:
            self._background_thread.join()
        self.persist()
        BaseConnector.shutdown(self)

    def fetch_all(self) -> None:
        """
        Fetches all necessary data for the connector.

        This method calls the `fetch_vehicles` method to retrieve vehicle data.
        """
        self.fetch_vehicles()
        self.car_connectivity.transaction_end()

    def update_vehicles(self) -> None:
        """
        Updates the status of all vehicles in the garage managed by this connector.

        This method iterates through all vehicle VINs in the garage, and for each vehicle that is
        managed by this connector and is an instance of volvoVehicle, it updates the vehicle's status
        by fetching data from various APIs. If the vehicle is an instance of volvoElectricVehicle,
        it also fetches charging information.

        Returns:
            None
        """
        garage: Garage = self.car_connectivity.garage
        for vin in set(garage.list_vehicle_vins()):
            vehicle_to_update: Optional[GenericVehicle] = garage.get_vehicle(vin)
            if vehicle_to_update is not None and isinstance(vehicle_to_update, GenericVehicle) and vehicle_to_update.is_managed_by_connector(self):
                vehicle_to_update = self.fetch_odometer(vehicle_to_update)
                vehicle_to_update = self.fetch_windows(vehicle_to_update)
                vehicle_to_update = self.fetch_doors(vehicle_to_update)
                if self.location_session is not None:
                    vehicle_to_update = self.fetch_position(vehicle_to_update)
                self.decide_state(vehicle_to_update)

    def fetch_vehicles(self) -> None:
        """
        Fetches the list of vehicles from the volvo Connect API and updates the garage with new vehicles.
        This method sends a request to the volvo Connect API to retrieve the list of vehicles associated with the user's account.
        If new vehicles are found in the response, they are added to the garage.

        Returns:
            None
        """
        garage: Garage = self.car_connectivity.garage
        url = 'https://api.volvocars.com/connected-vehicle/v2/vehicles'
        # {'data': [{'vin': 'YV4952NA4F120DEMO'}, {'vin': 'LPSEFAVS2NPOLDEMO'}]}
        data: Dict[str, Any] | None = self._fetch_data(url, session=self.connected_vehicle_session)

        seen_vehicle_vins: set[str] = set()
        if data is not None:
            if 'data' in data and data['data'] is not None:
                for vehicle_dict in data['data']:
                    if 'vin' in vehicle_dict and vehicle_dict['vin'] is not None:
                        if vehicle_dict['vin'] in self.active_config['hide_vins']:
                            LOG.warning('Vehicle %s is hidden in config', vehicle_dict['vin'])
                            continue
                        vin: str = vehicle_dict['vin']
                        seen_vehicle_vins.add(vin)
                        vehicle: Optional[GenericVehicle] = garage.get_vehicle(vin)  # pyright: ignore[reportAssignmentType]
                        if vehicle is None:
                            vehicle = VolvoVehicle(vin=vin, garage=garage, managing_connector=self)
                            garage.add_vehicle(vin, vehicle)

                        url = f'https://api.volvocars.com/connected-vehicle/v2/vehicles/{vin}'
                        # {'data': {'vin': 'YV4952NA4F120DEMO', 'modelYear': 2019, 'gearbox': 'AUTOMATIC', 'fuelType': 'DIESEL', 'externalColour': 'SAVILE GREY', 'batteryCapacityKWH': 78.0, 'images': {'exteriorImageUrl': 'https://cas.volvocars.com/image/vbsnext-v4/exterior/MY19_1817/225/A8/13/49200/R131/_/TP02/_/_/TM02/JT02_f13/SR02/_/_/JB0C/T206/default.png?market=us&client=connected-vehicle-api&w=1920&bg=00000000&angle=0&fallback', 'internalImageUrl': 'https://cas.volvocars.com/image/vbsnext-v4/interior/MY19_1817/225/1/RC0000_f13/NC04/DI02/RU06/_/_/FJ01/EV02/K502/default.png?market=us&client=connected-vehicle-api&w=1920&bg=00000000&angle=0&fallback'}, 'descriptions': {'model': 'V60 II', 'upholstery': 'CHARCOAL/LEAC/CHARC', 'steering': 'LEFT'}}}
                        vehicle_data: Dict[str, Any] | None = self._fetch_data(url, session=self.connected_vehicle_session)

                        if vehicle_data is not None and 'data' in vehicle_data and vehicle_data['data'] is not None:
                            if 'modelYear' in vehicle_data['data'] and vehicle_data['data']['modelYear'] is not None:
                                vehicle.model_year._set_value(vehicle_data['data']['modelYear'])  # pylint: disable=protected-access

                            if 'gearbox' in vehicle_data['data'] and vehicle_data['data']['gearbox'] is not None:
                                if vehicle_data['data']['gearbox'] in [item.name for item in GenericVehicle.VehicleSpecification.GearboxType]:
                                    gearbox_type: GenericVehicle.VehicleSpecification.GearboxType = \
                                        GenericVehicle.VehicleSpecification.GearboxType[vehicle_data['data']['gearbox']]
                                    vehicle.specification.gearbox._set_value(gearbox_type)  # pylint: disable=protected-access
                                else:
                                    vehicle.specification.gearbox._set_value(GenericVehicle.VehicleSpecification.GearboxType.UNKNOWN)  # pylint: disable=protected-access
                                    LOG_API.warning('Unknown gearbox type: %s', vehicle_data['data']['gearbox'])
                            
                            if 'fuelType' in vehicle_data['data'] and vehicle_data['data']['fuelType'] is not None:
                                if vehicle_data['data']['fuelType'] in [item.name for item in GenericVehicle.Type]:
                                    car_type: GenericVehicle.Type = GenericVehicle.Type[vehicle_data['data']['fuelType']]
                                    vehicle.type._set_value(car_type)  # pylint: disable=protected-access
                                elif vehicle_data['data']['fuelType'] == 'PETROL/ELECTRIC':
                                    vehicle.type._set_value(GenericVehicle.Type.HYBRID)  # pylint: disable=protected-access
                                else:
                                    vehicle.type._set_value(GenericVehicle.Type.UNKNOWN)  # pylint: disable=protected-access
                                    LOG_API.warning('Unknown fuel type: %s', vehicle_data['data']['fuelType'])
                                if vehicle.type.value == GenericVehicle.Type.ELECTRIC and not isinstance(vehicle, VolvoElectricVehicle):
                                    LOG.debug('Promoting %s to VolvoElectricVehicle object for %s', vehicle.__class__.__name__, vin)
                                    vehicle = VolvoElectricVehicle(garage=self.car_connectivity.garage, origin=vehicle)
                                    self.car_connectivity.garage.replace_vehicle(vin, vehicle)
                                elif vehicle.type.value in [GenericVehicle.Type.FUEL,
                                                GenericVehicle.Type.GASOLINE,
                                                GenericVehicle.Type.PETROL,
                                                GenericVehicle.Type.DIESEL,
                                                GenericVehicle.Type.CNG,
                                                GenericVehicle.Type.LPG] \
                                        and not isinstance(vehicle, VolvoCombustionVehicle):
                                    LOG.debug('Promoting %s to VolvoCombustionVehicle object for %s', vehicle.__class__.__name__, vin)
                                    vehicle = VolvoCombustionVehicle(garage=self.car_connectivity.garage, origin=vehicle)
                                    self.car_connectivity.garage.replace_vehicle(vin, vehicle)
                                elif vehicle.type.value == GenericVehicle.Type.HYBRID and not isinstance(vehicle, VolvoHybridVehicle):
                                    LOG.debug('Promoting %s to VolvoHybridVehicle object for %s', vehicle.__class__.__name__, vin)
                                    vehicle = VolvoHybridVehicle(garage=self.car_connectivity.garage, origin=vehicle)
                                    self.car_connectivity.garage.replace_vehicle(vin, vehicle)
                            
                            if 'descriptions' in vehicle_data['data'] and vehicle_data['data']['descriptions'] is not None:
                                if 'model' in vehicle_data['data']['descriptions'] and vehicle_data['data']['descriptions']['model'] is not None:
                                    vehicle.model._set_value(vehicle_data['data']['descriptions']['model'])  # pylint: disable=protected-access
                                
                                if 'steering' in vehicle_data['data']['descriptions'] and vehicle_data['data']['descriptions']['steering'] is not None:
                                    if vehicle_data['data']['descriptions']['steering'] == 'LEFT':
                                        # pylint: disable-next=protected-access
                                        vehicle.specification.steering_wheel_position._set_value(GenericVehicle.VehicleSpecification.SteeringPosition.LEFT)
                                    elif vehicle_data['data']['descriptions']['steering'] == 'RIGHT':
                                        # pylint: disable-next=protected-access
                                        vehicle.specification.steering_wheel_position._set_value(GenericVehicle.VehicleSpecification.SteeringPosition.RIGHT)
                                    else:
                                        # pylint: disable-next=protected-access
                                        vehicle.specification.steering_wheel_position._set_value(GenericVehicle.VehicleSpecification.SteeringPosition.UNKNOWN)
                                        LOG_API.warning('Unknown steering position: %s', vehicle_data['data']['descriptions']['steering'])
                                log_extra_keys(LOG_API, 'descriptions', vehicle_data['data']['descriptions'], {'model', 'steering'})

                            if SUPPORT_IMAGES and 'images' in vehicle_data['data'] and vehicle_data['data']['images'] is not None:
                                # fetch vehcile images
                                for image_id, image_url in vehicle_data['data']['images'].items():
                                    img = None
                                    cache_date = None
                                    if self.active_config['max_age'] is not None and self.connected_vehicle_session.cache is not None and image_url in self.connected_vehicle_session.cache:
                                        img, cache_date_string = self.connected_vehicle_session.cache[image_url]
                                        img = base64.b64decode(img)  # pyright: ignore[reportPossiblyUnboundVariable]
                                        img = Image.open(io.BytesIO(img))  # pyright: ignore[reportPossiblyUnboundVariable]
                                        cache_date = datetime.fromisoformat(cache_date_string)
                                    if img is None or self.active_config['max_age'] is None \
                                            or (cache_date is not None and cache_date < (datetime.utcnow() - timedelta(seconds=self.active_config['max_age']))):
                                        try:
                                            headers = dict()
                                            # We need to pretend to be a browser to get the images
                                            headers['user-agent'] = 'Safari/605.1.15'
                                            image_download_response = requests.get(image_url, headers=headers, stream=True)
                                            if image_download_response.status_code == requests.codes['ok']:
                                                img = Image.open(image_download_response.raw)  # pyright: ignore[reportPossiblyUnboundVariable]
                                                if self.connected_vehicle_session.cache is not None:
                                                    buffered = io.BytesIO()  # pyright: ignore[reportPossiblyUnboundVariable]
                                                    img.save(buffered, format="PNG")
                                                    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")  # pyright: ignore[reportPossiblyUnboundVariable]
                                                    self.connected_vehicle_session.cache[image_url] = (img_str, str(datetime.utcnow()))
                                            else:
                                                print(f'Error: {image_download_response.text}')
                                                print(f'Error: {image_download_response.request.headers}')
                                        except requests.exceptions.ConnectionError as connection_error:
                                            raise RetrievalError(f'Connection error: {connection_error}') from connection_error
                                        except requests.exceptions.ChunkedEncodingError as chunked_encoding_error:
                                            raise RetrievalError(f'Error: {chunked_encoding_error}') from chunked_encoding_error
                                        except requests.exceptions.ReadTimeout as timeout_error:
                                            raise RetrievalError(f'Timeout during read: {timeout_error}') from timeout_error
                                        except requests.exceptions.RetryError as retry_error:
                                            raise RetrievalError(f'Retrying failed: {retry_error}') from retry_error
                                    if img is not None:
                                        vehicle._car_images[image_id] = img  # pylint: disable=protected-access
                                        if image_id == 'exteriorImageUrl':
                                            if 'car_picture' in vehicle.images.images:
                                                vehicle.images.images['car_picture']._set_value(img)  # pylint: disable=protected-access
                                            else:
                                                vehicle.images.images['car_picture'] = ImageAttribute(name="car_picture", parent=vehicle.images,
                                                                                                      value=img, tags={'carconnectivity'})
                            log_extra_keys(LOG_API, 'https://api.volvocars.com/connected-vehicle/v2/vehicles/{vin}', vehicle_data['data'],
                                           {'vin', 'modelYear', 'gearbox', 'descriptions', 'images'})
                    else:
                        raise APIError('Could not fetch vehicle data, VIN missing')
        for vin in set(garage.list_vehicle_vins()) - seen_vehicle_vins:
            vehicle_to_remove = garage.get_vehicle(vin)
            if vehicle_to_remove is not None and vehicle_to_remove.is_managed_by_connector(self):
                garage.remove_vehicle(vin)
        self.update_vehicles()

    def decide_state(self, vehicle: GenericVehicle) -> GenericVehicle:
        """
        Decides the state of the vehicle based on the current data.

        Args:
            vehicle (GenericVehicle): The volvo vehicle object.
        """
        return vehicle


    def fetch_position(self, vehicle: GenericVehicle) -> GenericVehicle:
        """
        Fetches the parking position of the given volvo vehicle and updates the vehicle's position attributes.

        Args:
            vehicle (GenericVehicle): The volvo vehicle object whose parking position is to be fetched.

        Raises:
            ValueError: If the vehicle's VIN is None.
            APIError: If the fetched data does not contain 'carCapturedTimestamp' or it is None.

        Updates:
            vehicle.position.latitude: The latitude of the vehicle's parking position.
            vehicle.position.longitude: The longitude of the vehicle's parking position.
        """
        vin = vehicle.vin.value
        if vin is None:
            raise ValueError('vehicle.vin cannot be None')
        url: str = f'https://api.volvocars.com/location/v1/vehicles/{vin}/location'
        data: Dict[str, Any] | None = self._fetch_data(url, self.location_session, allow_empty=True)
        if data is not None and 'data' in data and data['data'] is not None:
            if 'type' in data['data'] and data['data']['type'] == 'Feature':
                if 'properties' in data['data'] and data['data']['properties'] is not None:
                    if 'heading' in data['data']['properties'] and data['data']['properties']['heading'] is not None:
                        vehicle.position.heading._set_value(data['data']['properties']['heading'])  # pylint: disable=protected-access
                    else:
                        vehicle.position.heading._set_value(None)  # pylint: disable=protected-access
                    if 'timestamp' in data['data']['properties'] and data['data']['properties']['timestamp'] is not None:
                        captured_at: datetime = robust_time_parse(data['data']['properties']['timestamp'])
                    else:
                        raise APIError('Could not fetch position, timestamp missing')
                    if 'geometry' in data['data'] and data['data']['geometry'] is not None and data['data']['geometry']['type'] == 'Point':
                        if 'coordinates' in data['data']['geometry'] and data['data']['geometry']['coordinates'] is not None:
                            vehicle.position.latitude._set_value(data['data']['geometry']['coordinates'][1], measured=captured_at)  # pylint: disable=protected-access
                            vehicle.position.longitude._set_value(data['data']['geometry']['coordinates'][0], measured=captured_at)  # pylint: disable=protected-access
                            vehicle.position.altitude._set_value(data['data']['geometry']['coordinates'][2], measured=captured_at)  # pylint: disable=protected-access
                            vehicle.position.position_type._set_value(Position.PositionType.PARKING, measured=captured_at)  # pylint: disable=protected-access
                    else:
                        vehicle.position.latitude._set_value(None)  # pylint: disable=protected-access
                        vehicle.position.longitude._set_value(None)  # pylint: disable=protected-access
                        vehicle.position.altitude._set_value(None)  # pylint: disable=protected-access
                        vehicle.position.position_type._set_value(None)  # pylint: disable=protected-access
        else:
            vehicle.position.latitude._set_value(None)  # pylint: disable=protected-access
            vehicle.position.longitude._set_value(None)  # pylint: disable=protected-access
            vehicle.position.altitude._set_value(None)  # pylint: disable=protected-access
            vehicle.position.position_type._set_value(None)  # pylint: disable=protected-access
        return vehicle

    def fetch_windows(self, vehicle: GenericVehicle) -> GenericVehicle:
        vin = vehicle.vin.value
        if vin is None:
            raise ValueError('vehicle.vin cannot be None')
        url: str = f'https://api.volvocars.com/connected-vehicle/v2/vehicles/{vin}/windows'
        data: Dict[str, Any] | None = self._fetch_data(url, self.connected_vehicle_session, allow_empty=True)
        seen_window_ids: set[str] = set()
        if data is not None and 'data' in data and data['data'] is not None:
            for window_id, window_dict in data['data'].items():
                window_id = window_id.replace('Window', '')
                seen_window_ids.add(window_id)
                if window_id in vehicle.windows.windows:
                    window: Windows.Window = vehicle.windows.windows[window_id]
                else:
                    window = Windows.Window(window_id=window_id, windows=vehicle.windows)
                    vehicle.windows.windows[window_id] = window
                if 'timestamp' in window_dict and window_dict['timestamp'] is not None:
                    captured_at: datetime = robust_time_parse(window_dict['timestamp'])
                else:
                    raise APIError('Could not fetch window, timestamp missing')
                if 'value' in window_dict and window_dict['value'] is not None:
                    if window_dict['value'] in [item.name for item in Windows.OpenState]:
                        window.open_state._set_value(Windows.OpenState[window_dict['value']], measured=captured_at)  # pylint: disable=protected-access
                    else:
                        window.open_state._set_value(Windows.OpenState.UNKNOWN, measured=captured_at)  # pylint: disable=protected-access
                        LOG_API.warning('Unknown window state: %s', window_dict['value'])
                else:
                    window.open_state._set_value(None)  # pylint: disable=protected-access
        for window_id in vehicle.windows.windows.keys() - seen_window_ids:
            vehicle.windows.windows[window_id].enabled = False
        return vehicle

    def fetch_doors(self, vehicle: GenericVehicle) -> GenericVehicle:
        vin = vehicle.vin.value
        if vin is None:
            raise ValueError('vehicle.vin cannot be None')
        url: str = f'https://api.volvocars.com/connected-vehicle/v2/vehicles/{vin}/doors'
        data: Dict[str, Any] | None = self._fetch_data(url, self.connected_vehicle_session, allow_empty=True)
        seen_door_ids: set[str] = set()
        if data is not None and 'data' in data and data['data'] is not None:
            any_door_open: bool = False
            for door_id, door_dict in data['data'].items():
                door_id = door_id.replace('Door', '')
                if door_id == 'centralLock':
                    if 'value' in door_dict and door_dict['value'] is not None:
                        if door_dict['value'] == "LOCKED":
                            vehicle.doors.lock_state._set_value(Doors.LockState.LOCKED)  # pylint: disable=protected-access
                        elif door_dict['value'] == "UNLOCKED":
                            vehicle.doors.lock_state._set_value(Doors.LockState.UNLOCKED)  # pylint: disable=protected-access
                        else:
                            vehicle.doors.lock_state._set_value(Doors.LockState.UNKNOWN)  # pylint: disable=protected-access
                else:
                    seen_door_ids.add(door_id)
                    if door_id in vehicle.doors.doors:
                        door: Doors.Door = vehicle.doors.doors[door_id]
                    else:
                        door = Doors.Door(door_id=door_id, doors=vehicle.doors)
                        vehicle.doors.doors[door_id] = door
                    if 'timestamp' in door_dict and door_dict['timestamp'] is not None:
                        captured_at: datetime = robust_time_parse(door_dict['timestamp'])
                    else:
                        raise APIError('Could not fetch door, timestamp missing')
                    if 'value' in door_dict and door_dict['value'] is not None:
                        if door_dict['value'] == "UNSPECIFIED":
                            door.open_state._set_value(Doors.OpenState.UNKNOWN, measured=captured_at)  # pylint: disable=protected-access
                        elif door_dict['value'] in [item.name for item in Doors.OpenState]:
                            door.open_state._set_value(Doors.OpenState[door_dict['value']], measured=captured_at)  # pylint: disable=protected-access
                        else:
                            door.open_state._set_value(Windows.OpenState.UNKNOWN, measured=captured_at)  # pylint: disable=protected-access
                            LOG_API.warning('Unknown door state: %s', door_dict['value'])
                        if door.open_state.value in [Doors.OpenState.OPEN, Doors.OpenState.AJAR]:
                            any_door_open = True
                    else:
                        door.open_state._set_value(None)  # pylint: disable=protected-access
                    door.lock_state._set_value(vehicle.doors.lock_state.value)  # pylint: disable=protected-access
            if any_door_open:
                vehicle.doors.open_state._set_value(Doors.OpenState.OPEN)  # pylint: disable=protected-access
            else:
                vehicle.doors.open_state._set_value(Doors.OpenState.CLOSED)  # pylint: disable=protected-access
        for door_id in vehicle.doors.doors.keys() - seen_door_ids:
            vehicle.doors.doors[door_id].enabled = False
        return vehicle

    def fetch_odometer(self, vehicle: GenericVehicle) -> GenericVehicle:
        vin = vehicle.vin.value
        if vin is None:
            raise ValueError('vehicle.vin cannot be None')
        url: str = f'https://api.volvocars.com/connected-vehicle/v2/vehicles/{vin}/odometer'
        data: Dict[str, Any] | None = self._fetch_data(url, self.connected_vehicle_session, allow_empty=True)
        if data is not None and 'data' in data and data['data'] is not None:
            if 'odometer' in data['data'] and data['data']['odometer'] is not None:
                if 'timestamp' in data['data']['odometer'] and data['data']['odometer']['timestamp'] is not None:
                    captured_at: datetime = robust_time_parse(data['data']['odometer']['timestamp'])
                else:
                    raise APIError('Could not fetch odometer, timestamp missing')
                if 'unit' in data['data']['odometer'] and data['data']['odometer']['unit'] is not None and data['data']['odometer']['unit'] == 'km':
                    unit = Length.KM
                else:
                    unit = Length.KM
                    LOG_API.warning('Unknown odometer unit: %s', data['data']['odometer']['unit'])
                if 'value' in data['data']['odometer'] and data['data']['odometer']['value'] is not None:
                    vehicle.odometer._set_value(data['data']['odometer']['value'], measured=captured_at, unit=unit)  # pylint: disable=protected-access
        return vehicle

    def _record_elapsed(self, elapsed: timedelta) -> None:
        """
        Records the elapsed time.

        Args:
            elapsed (timedelta): The elapsed time to record.
        """
        self._elapsed.append(elapsed)

    def _fetch_data(self, url, session, force=False, allow_empty=False, allow_http_error=False, allowed_errors=None) -> Optional[Dict[str, Any]]:  # noqa: C901
        data: Optional[Dict[str, Any]] = None
        cache_date: Optional[datetime] = None
        if not force and (self.active_config['max_age'] is not None and session.cache is not None and url in session.cache):
            data, cache_date_string = session.cache[url]
            cache_date = datetime.fromisoformat(cache_date_string)
        if data is None or self.active_config['max_age'] is None \
                or (cache_date is not None and cache_date < (datetime.utcnow() - timedelta(seconds=self.active_config['max_age']))):
            try:
                status_response: requests.Response = session.get(url, allow_redirects=False)
                self._record_elapsed(status_response.elapsed)
                if status_response.status_code in (requests.codes['ok'], requests.codes['multiple_status']):
                    data = status_response.json()
                    if session.cache is not None:
                        session.cache[url] = (data, str(datetime.utcnow()))
                elif status_response.status_code == requests.codes['no_content'] and allow_empty:
                    data = None
                elif status_response.status_code == requests.codes['too_many_requests']:
                    raise TooManyRequestsError('Could not fetch data due to too many requests from your account. '
                                               f'Status Code was: {status_response.status_code}')
                elif status_response.status_code == requests.codes['unauthorized']:
                    LOG.info('Server asks for new authorization')
                    session.login()
                    status_response = session.get(url, allow_redirects=False)

                    if status_response.status_code in (requests.codes['ok'], requests.codes['multiple_status']):
                        data = status_response.json()
                        if session.cache is not None:
                            session.cache[url] = (data, str(datetime.utcnow()))
                    elif not allow_http_error or (allowed_errors is not None and status_response.status_code not in allowed_errors):
                        raise RetrievalError(f'Could not fetch data even after re-authorization. Status Code was: {status_response.status_code}')
                elif not allow_http_error or (allowed_errors is not None and status_response.status_code not in allowed_errors):
                    raise RetrievalError(f'Could not fetch data for {url}. Status Code was: {status_response.status_code}')
            except requests.exceptions.ConnectionError as connection_error:
                raise RetrievalError(f'Connection error: {connection_error}') from connection_error
            except requests.exceptions.ChunkedEncodingError as chunked_encoding_error:
                raise RetrievalError(f'Error: {chunked_encoding_error}') from chunked_encoding_error
            except requests.exceptions.ReadTimeout as timeout_error:
                raise RetrievalError(f'Timeout during read: {timeout_error}') from timeout_error
            except requests.exceptions.RetryError as retry_error:
                raise RetrievalError(f'Retrying failed: {retry_error}') from retry_error
            except requests.exceptions.JSONDecodeError as json_error:
                if allow_empty:
                    data = None
                else:
                    raise RetrievalError(f'JSON decode error: {json_error}') from json_error
        return data

    def get_version(self) -> str:
        return __version__

    def get_type(self) -> str:
        return "carconnectivity-connector-volvo"

    def get_name(self) -> str:
        return "Volvo Connector"
