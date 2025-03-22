
"""
This module provides utility functions and classes for handling authentication and parsing HTML forms
and scripts for the Volvo car connectivity connector.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional, Dict


def add_bearer_auth_header(token, headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Adds a Bearer token to the Authorization header.

    Args:
        token (str): The Bearer token to be added to the headers.
        headers (Optional[Dict[str, str]]): An optional dictionary of headers to which the Authorization header will be added.
                                            If not provided, a new dictionary will be created.

    Returns:
        Dict[str, str]: The headers dictionary with the added Authorization header.
    """
    headers = headers or {}
    headers['Authorization'] = f'Bearer {token}'
    return headers
