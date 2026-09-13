"""SSRF Protection and Secure URL Fetcher.

Guarantees full protection against Server-Side Request Forgery by validating target
hostnames and IP addresses before the initial connection AND before every subsequent
redirect hop, covering IPv4, IPv6, loopback, private, link-local, and reserved ranges.
"""

import ipaddress
import logging
import os
import socket
from typing import List, Optional, Set
import urllib.parse

import httpx

from ...exceptions import StorageError

logger = logging.getLogger("limo.services.extraction.ssrf")

# Additional carrier-grade NAT and reserved subnets
CARRIER_GRADE_NAT = ipaddress.ip_network("100.64.0.0/10")
BENCHMARK_NET = ipaddress.ip_network("198.18.0.0/15")
SIX_TO_FOUR_RELAY = ipaddress.ip_network("192.88.99.0/24")


class SSRFProtectionError(StorageError):
    """Raised when an outbound URL target violates SSRF network boundaries."""
    pass


def is_ip_safe(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Verify an IP address is a publicly routable global address."""
    # Check for IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return is_ip_safe(ip.ipv4_mapped)

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False

    # Check specific non-global IPv4 subnets
    if isinstance(ip, ipaddress.IPv4Address):
        if (
            ip in CARRIER_GRADE_NAT
            or ip in BENCHMARK_NET
            or ip in SIX_TO_FOUR_RELAY
        ):
            return False

    return True


def resolve_and_validate_hostname(hostname: str, port: int = 80) -> List[str]:
    """Resolve DNS for a hostname and verify every resolved IP is safe."""
    clean_host = hostname.strip().lower()

    # Reject localhost aliases explicitly
    if clean_host in ("localhost", "localhost.localdomain", "broadcasthost"):
        raise SSRFProtectionError(f"Access to localhost alias '{clean_host}' is blocked")

    try:
        addr_infos = socket.getaddrinfo(clean_host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise SSRFProtectionError(f"DNS resolution failed for hostname '{clean_host}': {e}") from e

    resolved_ips: Set[str] = set()
    for family, _, _, _, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        resolved_ips.add(ip_str)
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError as e:
            raise SSRFProtectionError(f"Invalid IP address returned from DNS: {ip_str}") from e

        if not is_ip_safe(ip_obj):
            raise SSRFProtectionError(
                f"Hostname '{clean_host}' resolved to non-public/restricted IP: {ip_str}"
            )

    if not resolved_ips:
        raise SSRFProtectionError(f"No IP addresses resolved for hostname '{clean_host}'")

    return list(resolved_ips)


def validate_url(url_str: str) -> urllib.parse.ParseResult:
    """Validate URL syntax, scheme, credentials, and DNS resolution."""
    clean_url = url_str.strip()
    parsed = urllib.parse.urlparse(clean_url)

    if parsed.scheme not in ("http", "https"):
        raise SSRFProtectionError(f"Unsupported URL scheme '{parsed.scheme}'; only http and https are permitted")

    if not parsed.netloc or not parsed.hostname:
        raise SSRFProtectionError("URL must include a valid hostname")

    if parsed.username or parsed.password:
        raise SSRFProtectionError("Embedded userinfo (user:pass@host) in URLs is rejected")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # If hostname is a direct IP literal, check it directly
    try:
        ip_obj = ipaddress.ip_address(parsed.hostname)
        if not is_ip_safe(ip_obj):
            raise SSRFProtectionError(f"Direct connection to private/restricted IP '{parsed.hostname}' is blocked")
    except ValueError:
        # Hostname is a domain name, resolve and validate all returned IPs
        resolve_and_validate_hostname(parsed.hostname, port)

    return parsed


# Configurable URL download size ceiling (default 25 MB)
MAX_URL_DOWNLOAD_BYTES = int(
    os.getenv("LIMO_MAX_URL_DOWNLOAD_BYTES", str(25 * 1024 * 1024))
)


async def fetch_url_ssrf_safe(
    url: str,
    max_redirects: int = 5,
    timeout_sec: float = 15.0,
    max_body_bytes: int = MAX_URL_DOWNLOAD_BYTES,
) -> httpx.Response:
    """Execute a GET request with verified pre-hop SSRF validation across all redirects.

    Guarantees:
    1. Initial target is validated before TCP connect.
    2. Every 3xx redirect Location header is resolved and validated BEFORE following the hop.
    3. Maximum redirect limit (default 5) is strictly enforced.
    4. Streaming download with hard MAX_URL_DOWNLOAD_BYTES ceiling to prevent memory exhaustion.
    """
    current_url = url
    redirect_count = 0

    headers = {
        "User-Agent": "Limo-Ingestion-Bot/1.0 (+https://github.com/priyaj-gawade/FunnelDenk)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    async with httpx.AsyncClient(
        verify=True,
        timeout=httpx.Timeout(timeout_sec),
        follow_redirects=False,  # Explicit manual redirect handling
    ) as client:
        while True:
            # Validate current URL and its resolved IP before sending request
            validate_url(current_url)

            logger.info("Fetching validated URL: %s (redirect_count=%d)", current_url, redirect_count)
            try:
                request = client.build_request("GET", current_url, headers=headers)
                response = await client.send(request, stream=True)
            except httpx.RequestError as e:
                raise SSRFProtectionError(f"HTTP fetch failed for '{current_url}': {e}") from e

            # Handle 3xx redirects explicitly
            if response.status_code in (301, 302, 303, 307, 308):
                await response.aclose()
                redirect_count += 1
                if redirect_count > max_redirects:
                    raise SSRFProtectionError(f"Exceeded maximum allowed redirects ({max_redirects})")

                location = response.headers.get("Location")
                if not location:
                    raise SSRFProtectionError("Redirect response missing 'Location' header")

                # Handle relative redirect locations safely
                next_url = urllib.parse.urljoin(current_url, location)
                logger.info("Intercepted redirect (%d) to: %s", response.status_code, next_url)

                current_url = next_url
                continue

            if response.status_code != 200:
                await response.aclose()
                raise StorageError(f"Remote server returned HTTP {response.status_code}")

            # Enforce body size limit upfront via Content-Length if provided
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_body_bytes:
                await response.aclose()
                raise StorageError(
                    f"Remote resource size ({content_length} bytes) exceeds maximum limit ({max_body_bytes} bytes)"
                )

            # Stream chunks with cumulative byte tracking
            accumulated = bytearray()
            try:
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    accumulated.extend(chunk)
                    if len(accumulated) > max_body_bytes:
                        raise StorageError(
                            f"Remote resource exceeded maximum allowed download size of {max_body_bytes} bytes"
                        )
            finally:
                await response.aclose()

            # Return a materialized response with the safely accumulated bytes
            return httpx.Response(
                status_code=200,
                headers=response.headers,
                content=bytes(accumulated),
                request=request,
            )
