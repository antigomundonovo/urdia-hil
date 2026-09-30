"""SSRF-safe fetcher (Doc 08 "SSRF" + Doc 09 "Fetch safety").

Rules enforced here, all spec-mandated:
- only http/https schemes (file:// and local sockets never leave this module);
- every redirect hop is revalidated — destination DNS re-resolved and checked
  against loopback/private/link-local/reserved ranges before following
  (redirect revalidation, Doc 08);
- timeouts and a hard response size limit;
- robots.txt respected (robots handling, Doc 09) with a per-host cache;
- per-host rate limiting (simple in-memory minimum interval);
- ETag/Last-Modified surfaced for conditional requests (Doc 09 caching).
"""

import fnmatch
import ipaddress
import socket
import time
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

DEFAULT_MAX_REDIRECTS = 5
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_MIN_HOST_INTERVAL_SECONDS = 1.0

BLOCKED_HOST_PATTERNS = ("localhost", "*.local", "*.internal")

Resolver = Callable[[str], list[str]]


def _default_resolver(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise FetchBlockedError(f"DNS resolution failed for {host}") from exc
    return sorted({info[4][0] for info in infos})


def _ip_allowed(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _host_allowed(host: str, resolver: Resolver) -> bool:
    lowered = (host or "").lower()
    if any(fnmatch.fnmatch(lowered, pat) for pat in BLOCKED_HOST_PATTERNS):
        raise FetchBlockedError(f"host not allowed: {lowered}")
    ips = resolver(lowered)
    if not ips:
        raise FetchBlockedError(f"no addresses for {lowered}")
    bad = {ip for ip in ips if not _ip_allowed(ip)}
    if bad:
        # fail closed: any private/reserved address blocks the host
        raise FetchBlockedError(f"blocked address(es) for {lowered}: {sorted(bad)}")
    return True


def validate_url(url: str, resolver: Resolver | None = None) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchBlockedError(f"scheme not allowed: {parsed.scheme or '(none)'}")
    if not parsed.hostname:
        raise FetchBlockedError("URL without hostname")
    _host_allowed(parsed.hostname, resolver or _default_resolver)
    return url


class FetchBlockedError(Exception):
    """Fail closed: the URL violates fetch policy (scheme, host, robots, size)."""


@dataclass
class FetchResult:
    url: str
    status_code: int
    content: bytes
    content_type: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    duration_ms: int = 0
    redirect_hops: int = 0


class _RateLimiter:
    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._last: dict[str, float] = {}

    def wait(self, host: str) -> None:
        now = time.monotonic()
        last = self._last.get(host)
        if last is not None and now - last < self.min_interval:
            time.sleep(self.min_interval - (now - last))
        self._last[host] = time.monotonic()


class SafeFetcher:
    def __init__(
        self,
        *,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_bytes: int = DEFAULT_MAX_BYTES,
        min_host_interval: float = DEFAULT_MIN_HOST_INTERVAL_SECONDS,
        respect_robots: bool = True,
        client: httpx.Client | None = None,
        robot_loader=None,
        resolver: Resolver | None = None,
    ) -> None:
        self.max_redirects = max_redirects
        self.max_bytes = max_bytes
        self._client = client
        self._timeout = timeout_seconds
        self._rate = _RateLimiter(min_host_interval)
        self._respect_robots = respect_robots
        self._robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._robot_loader = robot_loader  # injectable for tests
        self._resolver = resolver  # injectable for tests (no real DNS)

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self._timeout,
                follow_redirects=False,  # redirects are validated hop by hop
                headers={"User-Agent": "URDIA-HIL/0.4 (+local-first research fetcher)"},
            )
        return self._client

    def _robots_allows(self, url: str) -> bool:
        if not self._respect_robots:
            return True
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._robots_cache:
            parser = urllib.robotparser.RobotFileParser()
            robots_url = urljoin(base, "/robots.txt")
            try:
                if self._robot_loader is not None:
                    parser.parse(self._robot_loader(base).splitlines())
                else:
                    resp = self._http().get(robots_url, timeout=self._timeout)
                    parser.parse(resp.text.splitlines() if resp.status_code == 200 else [])
            except Exception:
                # unreachable robots → allow but do not cache the failure
                self._robots_cache[base] = None
                return True
            self._robots_cache[base] = parser
        parser = self._robots_cache[base]
        if parser is None:
            return True
        return parser.can_fetch("URDIA-HIL", url)

    def fetch(
        self, url: str, *, etag: str | None = None, last_modified: str | None = None
    ) -> FetchResult:
        """Fetch with hop-by-hop redirect revalidation. Returns FetchResult;
        raises FetchBlockedError on any policy violation."""
        current = validate_url(url, self._resolver)
        hops = 0
        started = time.monotonic()
        headers_in: dict[str, str] = {}
        if etag:
            headers_in["If-None-Match"] = etag
        if last_modified:
            headers_in["If-Modified-Since"] = last_modified

        while True:
            if hops > self.max_redirects:
                raise FetchBlockedError(f"too many redirects (> {self.max_redirects})")
            host = urlparse(current).hostname
            self._rate.wait(host)
            if not self._robots_allows(current):
                raise FetchBlockedError(f"robots.txt disallows: {current}")

            response = self._http().get(current, headers=headers_in)

            if response.status_code in (301, 302, 303, 307, 308):
                hops += 1
                location = response.headers.get("location", "")
                if not location:
                    raise FetchBlockedError("redirect without location")
                current = validate_url(urljoin(current, location), self._resolver)
                continue

            if response.status_code == 304:
                duration = int((time.monotonic() - started) * 1000)
                return FetchResult(
                    url=url,
                    status_code=304,
                    content=b"",
                    etag=response.headers.get("etag"),
                    last_modified=response.headers.get("last-modified"),
                    duration_ms=duration,
                    redirect_hops=hops,
                )

            content = response.content or b""
            if len(content) > self.max_bytes:
                raise FetchBlockedError(
                    f"response too large: {len(content)} > {self.max_bytes} bytes"
                )
            duration = int((time.monotonic() - started) * 1000)
            return FetchResult(
                url=url,
                status_code=response.status_code,
                content=content,
                content_type=response.headers.get("content-type"),
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
                duration_ms=duration,
                redirect_hops=hops,
            )
