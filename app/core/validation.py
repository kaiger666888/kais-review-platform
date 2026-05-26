"""Callback URL validation for SSRF mitigation.

Validates that callback URLs resolve to RFC1918 private IP addresses,
preventing Server-Side Request Forgery attacks on the review platform.
"""

import ipaddress
import socket
from urllib.parse import urlparse

# Private network ranges allowed for callback URLs
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),       # RFC1918 Class A
    ipaddress.ip_network("172.16.0.0/12"),    # RFC1918 Class B
    ipaddress.ip_network("192.168.0.0/16"),   # RFC1918 Class C
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback (local dev)
    ipaddress.ip_network("169.254.0.0/16"),   # Link-local (local dev)
]


def validate_callback_url(url: str | None) -> str | None:
    """Validate that a callback URL resolves to a private IP address.

    Args:
        url: The callback URL to validate, or None if no callback.

    Returns:
        The original URL if validation passes, or None if input is None.

    Raises:
        ValueError: If the URL resolves to a non-private IP address.
    """
    if url is None:
        return None

    parsed = urlparse(url)
    hostname = parsed.hostname

    if not hostname:
        raise ValueError("Callback URL must have a valid hostname")

    # Resolve hostname to IP address(es)
    try:
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_INET)
    except socket.gaierror as e:
        raise ValueError(f"Cannot resolve callback URL hostname: {hostname}") from e

    if not addr_infos:
        raise ValueError(f"Cannot resolve callback URL hostname: {hostname}")

    # Check the first resolved address
    ip_str = addr_infos[0][4][0]
    ip = ipaddress.ip_address(ip_str)

    for network in _PRIVATE_NETWORKS:
        if ip in network:
            return url

    raise ValueError(
        f"Callback URL must resolve to a private IP address, got {ip}"
    )
