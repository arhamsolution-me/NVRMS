"""SSRF Guard: IP and hostname validation for NVR discovery."""

from __future__ import annotations

import ipaddress
import socket

# Blocked subnets (cloud metadata, broadcast, multicast, unspecified)
DANGEROUS_NETWORKS = [
    ipaddress.ip_network("169.254.169.254/32"),  # AWS / GCP / Azure metadata endpoint
    ipaddress.ip_network("169.254.0.0/16"),  # IPv4 link-local
    ipaddress.ip_network("0.0.0.0/8"),  # This-network
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved / Future use
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
]

# Allowed private networks by default (RFC 1918 + loopback)
ALLOWED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback allowed for dev/tests and local simulators
]


class SSRFSecurityError(ValueError):
    """Raised when an IP or target fails SSRF validation."""


def validate_target_ip(target: str, allow_public: bool = False) -> str:
    """Validate that target IP address is a safe, non-metadata, private address.

    Args:
        target: IP address string or hostname.
        allow_public: If True, public IPs are permitted (default: False).

    Returns:
        The canonical IP string.

    Raises:
        SSRFSecurityError: If the target violates SSRF constraints.
    """
    clean_target = target.strip()
    if not clean_target:
        raise SSRFSecurityError("Target host cannot be empty")

    # Try parsing directly as an IP address
    try:
        ip = ipaddress.ip_address(clean_target)
    except ValueError:
        # Hostname resolution with short timeout
        try:
            resolved_ip_str = socket.gethostbyname(clean_target)
            ip = ipaddress.ip_address(resolved_ip_str)
        except Exception as exc:
            raise SSRFSecurityError(
                f"Failed to resolve target hostname '{clean_target}': {exc}"
            ) from exc

    # 1. Check against dangerous networks (always blocked)
    for bad_net in DANGEROUS_NETWORKS:
        if ip in bad_net:
            raise SSRFSecurityError(
                f"Target IP '{ip}' is in forbidden network '{bad_net}' (SSRF protection)"
            )

    # 2. Check private range constraint
    if not allow_public:
        is_allowed = any(ip in allowed_net for allowed_net in ALLOWED_NETWORKS)
        if not is_allowed:
            raise SSRFSecurityError(
                f"Target IP '{ip}' is not within allowed private IP ranges (SSRF protection)"
            )

    return str(ip)
