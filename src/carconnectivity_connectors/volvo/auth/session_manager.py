"""Module implementing the SessionManager class."""
from __future__ import annotations
from typing import TYPE_CHECKING, Tuple

from enum import Enum

import hashlib

import logging

from carconnectivity_connectors.volvo.auth.volvo_session import VolvoSession

if TYPE_CHECKING:
    from typing import Dict, Any

LOG = logging.getLogger("carconnectivity.connectors.volvo.auth")


class Service(Enum):
    """
    An enumeration representing different services.

    Attributes:
        VOLVO_CONNECTED_VEHICLE (str): Represents the 'Volvo Connected Vehicle' service.
        VOLVO_ENERGY (str): Represents the 'Volvo Energy' service.
        VOLVO_LOCATION (str): Represents the 'Volvo Location'

    Methods:
        __str__() -> str: Returns the string representation of the service.
    """
    VOLVO_CONNECTED_VEHICLE = 'VolvoConnectedVehicleAPI'
    VOLVO_ENERGY = 'VolvoEnergyAPI'
    VOLVO_LOCATION = 'VolvoLocationAPI'

    def __str__(self) -> str:
        return self.value


class SessionToken():
    """
    A class to represent a session token.

    Attributes:
    ----------
    access_token : str
        The access_token for the desired service.

    Methods:
    -------
    __str__():
        Returns a string representation of the session user in the format 'username:password'.
    """
    def __init__(self, vcc_api_key_primary, vcc_api_key_secondary, access_token: str) -> None:
        self.vcc_api_key_primary: str = vcc_api_key_primary
        self.vcc_api_key_secondary: str = vcc_api_key_secondary
        self.access_token: str = access_token

    def __str__(self) -> str:
        return f'{self.vcc_api_key_primary}:{self.vcc_api_key_secondary}:{self.access_token}'


class SessionManager():
    """
    Manages sessions for different services and users, handling token storage and caching.
    """
    def __init__(self, tokenstore: Dict[str, Any], cache:  Dict[str, Any]) -> None:
        self.tokenstore: Dict[str, Any] = tokenstore
        self.cache: Dict[str, Any] = cache
        self.sessions: Dict[Tuple[Service, SessionToken], VolvoSession] = {}

    @staticmethod
    def generate_hash(service: Service, session_token: SessionToken) -> str:
        """
        Generates a SHA-512 hash for the given service and session user.

        Args:
            service (Service): The service for which the hash is being generated.
            session_token (SessionToken): The session token for which the hash is being generated.

        Returns:
            str: The generated SHA-512 hash as a hexadecimal string.
        """
        hash_str: str = service.value + str(session_token)
        return hashlib.sha512(hash_str.encode()).hexdigest()

    @staticmethod
    def generate_identifier(service: Service, session_token: SessionToken) -> str:
        """
        Generate a unique identifier for a given service and session token.

        Args:
            service (Service): The service for which the identifier is being generated.
            session_token (SessionToken): The session token for which the identifier is being generated.

        Returns:
            str: A unique identifier string.
        """
        return 'CarConnectivity-connector-volvo:' + SessionManager.generate_hash(service, session_token)

    def get_session(self, service: Service, session_token: SessionToken) -> VolvoSession:
        """
        Retrieves a session for the given service and session user. If a session already exists in the sessions cache,
        it is returned. Otherwise, a new session is created using the token, metadata, and cache from the tokenstore
        and cache if available.

        Args:
            service (Service): The service for which the session is being requested.
            session_token (SessionToken): The user for whom the session is being requested.

        Returns:
            Session: The session object for the given service and session user.
        """
        session = None
        if (service, session_token) in self.sessions:
            return self.sessions[(service, session_token)]

        identifier: str = SessionManager.generate_identifier(service, session_token)
        token = None
        cache = {}
        metadata = {}

        if identifier in self.tokenstore:
            if 'token' in self.tokenstore[identifier]:
                LOG.info('Reusing tokens from previous session')
                token = self.tokenstore[identifier]['token']
            if 'metadata' in self.tokenstore[identifier]:
                metadata = self.tokenstore[identifier]['metadata']
        if identifier in self.cache:
            cache = self.cache[identifier]

        if service == Service.VOLVO_CONNECTED_VEHICLE:
            session = VolvoSession(vcc_api_key_primary=session_token.vcc_api_key_primary, vcc_api_key_secondary=session_token.vcc_api_key_secondary,
                                   access_token=session_token.access_token, cache=cache)
        else:
            raise ValueError(f"Unsupported service: {service}")

        self.sessions[(service, session_token)] = session
        return session

    def persist(self) -> None:
        """
        Persist the current sessions into the token store and cache.

        This method iterates over the sessions and stores each session's token and metadata
        in the token store using a generated identifier. It also stores the session's cache
        in the cache.
        """
        for (service, user), session in self.sessions.items():
            identifier: str = SessionManager.generate_identifier(service, user)
            self.tokenstore[identifier] = {}
            self.tokenstore[identifier]['token'] = session.token
            self.tokenstore[identifier]['metadata'] = session.metadata
            self.cache[identifier] = session.cache
