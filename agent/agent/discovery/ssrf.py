"""SSRF Guard: IP and hostname validation for NVR discovery."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Sequence

from agent.logging_config import get_logger

log = get_logger(__name__)

# Blocked subnets (cloud metadata, broadcast, multicast, unspecified)
DANGEROUS_NETWORKS = [
    ipaddress.ip_network("169.254.169.254/32"),  # AWS / GCP / Azure metadata endpoint
    ipaddress.ip_network("169.254.0.0/16"),  # IPv4 link-local
    ipaddress.ip_network("0.0.0.0/8"),  # This-network
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved / Future use
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
]

LOOPBACK_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
]

# Allowed private RFC 1918 networks by default
ALLOWED_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]


class SSRFSecurityError(ValueError):
    """Raised when an IP or target fails SSRF validation."""


def validate_target_ip(
    target: str,
    allow_public: bool = False,
    allow_loopback: bool = True,
    blocked_hosts: Sequence[str] | None = None,
) -> str:
    """Validate that target IP address is a safe, non-metadata, private address.

    Args:
        target: IP address string or hostname.
        allow_public: If True, public IPs are permitted (default: False).
        allow_loopback: If True, loopback addresses (127.0.0.0/8) are permitted for local tests.
            When False (hardened mode), loopback is strictly blocked.
        blocked_hosts: Optional list of additional forbidden hosts (e.g., Hub server IP).

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
            log.warning("ssrf_dns_resolution_failed", target=clean_target, error=str(exc))
            raise SSRFSecurityError(
                f"Failed to resolve target hostname '{clean_target}': {exc}"
            ) from exc

    # 1. Check against dangerous networks (always blocked)
    for bad_net in DANGEROUS_NETWORKS:
        if ip in bad_net:
            log.warning(
                "ssrf_attempt_blocked",
                target=clean_target,
                ip=str(ip),
                network=str(bad_net),
                reason="metadata_or_dangerous_network",
            )
            raise SSRFSecurityError(
                f"Target IP '{ip}' is in forbidden network '{bad_net}' (SSRF protection)"
            )

    # 2. Check loopback constraints
    for loopback_net in LOOPBACK_NETWORKS:
        if ip in loopback_net:
            if not allow_loopback:
                log.warning(
                    "ssrf_attempt_blocked",
                    target=clean_target,
                    ip=str(ip),
                    reason="loopback_probe_forbidden",
                )
                raise SSRFSecurityError(
                    f"Target IP '{ip}' is a loopback address and forbidden in hardened mode (SSRF protection)"
                )
            return str(ip)

    # 3. Check explicit blocked hosts (e.g. Hub IP pivot defense)
    if blocked_hosts:
        for b in blocked_hosts:
            try:
                b_ip = ipaddress.ip_address(b.strip())
                if ip == b_ip:
                    log.warning(
                        "ssrf_attempt_blocked",
                        target=clean_target,
                        ip=str(ip),
                        reason="hub_target_forbidden",
                    )
                    raise SSRFSecurityError(
                        f"Target IP '{ip}' matches forbidden infrastructure host (SSRF protection)"
                    )
            except ValueError as err:
                if clean_target.lower() == b.strip().lower():
                    raise SSRFSecurityError(
                        f"Target host '{clean_target}' matches forbidden infrastructure host"
                    ) from err

    # 4. Check private range constraint
    if not allow_public:
        is_allowed = any(ip in allowed_net for allowed_net in ALLOWED_PRIVATE_NETWORKS)
        if not is_allowed:
            log.warning(
                "ssrf_attempt_blocked",
                target=clean_target,
                ip=str(ip),
                reason="non_private_ip",
            )
            raise SSRFSecurityError(
                f"Target IP '{ip}' is not within allowed private IP ranges (SSRF protection)"
            )

    return str(ip)
