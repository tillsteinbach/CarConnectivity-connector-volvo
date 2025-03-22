"""Implements a session class that handles OpenID authentication."""
from __future__ import annotations
from typing import TYPE_CHECKING

import logging
import requests

from oauthlib.oauth2.rfc6749.errors import InsecureTransportError, MissingTokenError
from oauthlib.oauth2.rfc6749.utils import is_secure_transport

from requests.adapters import HTTPAdapter

from carconnectivity_connectors.volvo.auth.auth_util import add_bearer_auth_header
from carconnectivity_connectors.volvo.auth.helpers.blacklist_retry import BlacklistRetry

if TYPE_CHECKING:
    from typing import Dict

LOG = logging.getLogger("carconnectivity.connectors.volvo.auth")


class VolvoSession(requests.Session):
    """
    VolvoSession is a subclass of requests.Session that handles OAuth Tokens for authentication.
    """
    def __init__(self, vcc_api_key_primary, vcc_api_key_secondary, access_token, timeout=None, cache=None, **kwargs) -> None:
        super(VolvoSession, self).__init__(**kwargs)

        self.timeout = timeout
        self._access_token = access_token
        self._retries: bool | int = False
        self.cache = cache
        self.headers.update({'vcc-api-key': vcc_api_key_primary})

    @property
    def retries(self) -> bool | int:
        """
        Get the number of retries.

        Returns:
            bool | int: The number of retries. It can be a boolean or an integer.
        """
        return self._retries

    @retries.setter
    def retries(self, new_retries_value):
        """
        Set the number of retries for the session and configure retry behavior.

        Args:
            new_retries_value (int): The new number of retries to set. If provided,
                                     configures the session to retry on internal server
                                     errors (HTTP status code 500) and blacklist status
                                     code 429 with a backoff factor of 0.1.

        """
        self._retries = new_retries_value
        if new_retries_value:
            # Retry on internal server error (500)
            retries = BlacklistRetry(total=new_retries_value,
                                     backoff_factor=0.1,
                                     status_forcelist=[500],
                                     status_blacklist=[429],
                                     raise_on_status=False)
            self.mount('https://', HTTPAdapter(max_retries=retries))

    @property
    def token(self):
        """
        Retrieve the current token.

        Returns:
            str: The current token.
        """
        return self._access_token

    def request(  # noqa: C901
        self,
        method,
        url,
        data=None,
        headers=None,
        timeout=None,
        token=None,
        **kwargs
    ) -> requests.Response:
        """Intercept all requests and add the OAuth 2 token if present."""
        if not is_secure_transport(url):
            raise InsecureTransportError()

        url, headers, data = self.add_token(url, body=data, headers=headers, token=token)

        if timeout is None:
            timeout = self.timeout

        return super(VolvoSession, self).request(
            method, url, headers=headers, data=data, timeout=timeout, **kwargs
        )

    def add_token(self, uri, body=None, headers=None, token=None, **_):  # pylint: disable=too-many-arguments
        """
        Adds an authorization token to the request headers based on the specified access type.

        Args:
            uri (str): The URI to which the request is being made.
            body (Optional[Any]): The body of the request. Defaults to None.
            headers (Optional[Dict[str, str]]): The headers of the request. Defaults to None.
            access_type (AccessType): The type of access token to use (ID, REFRESH, or ACCESS). Defaults to AccessType.ACCESS.
            token (Optional[str]): The token to use. If None, the method will use the appropriate token based on the access_type. Defaults to None.
            **_ (Any): Additional keyword arguments.

        Raises:
            InsecureTransportError: If the URI does not use a secure transport (HTTPS).
            MissingTokenError: If the required token (ID, REFRESH, or ACCESS) is missing.

        Returns:
            Tuple[str, Dict[str, str], Optional[Any]]: The URI, updated headers with the authorization token, and the body of the request.
        """
        # Check if the URI uses a secure transport
        if not is_secure_transport(uri):
            raise InsecureTransportError()

        # Only add token if it is not explicitly withheld
        if token is None:
            if self._access_token is None:
                raise MissingTokenError()
            token = self._access_token

        return_headers: Dict[str, str] = add_bearer_auth_header(token, headers)

        return (uri, return_headers, body)
