"""SafeFetcher tests (Doc 08 SSRF + Doc 09 fetch safety) — httpx MockTransport,
fake resolver: no real network, no real DNS."""

import httpx
import pytest

from packages.research.fetcher import FetchBlockedError, SafeFetcher, validate_url

PUBLIC_IP = "93.184.216.34"


def _fake_resolver(mapping: dict[str, list[str]]):
    import ipaddress

    def resolve(host: str) -> list[str]:
        try:
            ipaddress.ip_address(host)  # literal IP resolves to itself
            return [host]
        except ValueError:
            pass
        if host in mapping:
            return mapping[host]
        return [PUBLIC_IP]

    return resolve


def _transport(pages: dict[str, httpx.Response]):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in pages:
            return pages[url]
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _fetcher(client, mapping=None, **kwargs) -> SafeFetcher:
    return SafeFetcher(
        client=client,
        respect_robots=False,
        min_host_interval=0.0,
        resolver=_fake_resolver(mapping or {}),
        **kwargs,
    )


def test_simple_fetch_ok():
    client = _transport({"http://public.test/feed": httpx.Response(200, content=b"<rss>ok</rss>")})
    result = _fetcher(client).fetch("http://public.test/feed")
    assert result.status_code == 200
    assert result.content == b"<rss>ok</rss>"


def test_file_scheme_blocked():
    client = _transport({})
    with pytest.raises(FetchBlockedError, match="scheme"):
        _fetcher(client).fetch("file:///etc/passwd")


def test_localhost_blocked():
    client = _transport({})
    with pytest.raises(FetchBlockedError):
        _fetcher(client).fetch("http://localhost:8000/api")


def test_private_ip_blocked():
    client = _transport({})
    for bad in ("http://192.168.1.1/", "http://10.0.0.5/", "http://172.16.0.9/"):
        with pytest.raises(FetchBlockedError, match="blocked address"):
            _fetcher(client).fetch(bad)


def test_metadata_endpoint_blocked():
    client = _transport({})
    with pytest.raises(FetchBlockedError):
        _fetcher(client).fetch("http://169.254.169.254/latest/meta-data/")


def test_redirect_to_public_followed():
    client = _transport(
        {
            "http://public.test/a": httpx.Response(302, headers={"location": "http://public.test/b"}),
            "http://public.test/b": httpx.Response(200, content=b"final"),
        }
    )
    result = _fetcher(client).fetch("http://public.test/a")
    assert result.status_code == 200
    assert result.redirect_hops == 1
    assert result.content == b"final"


def test_redirect_to_private_blocked():
    """Doc 08: revalidar destino a cada redirect."""
    client = _transport(
        {
            "http://public.test/start": httpx.Response(302, headers={"location": "http://10.0.0.9/secret"}),
        }
    )
    with pytest.raises(FetchBlockedError, match="blocked address"):
        _fetcher(client).fetch("http://public.test/start")


def test_too_many_redirects_blocked():
    pages = {
        f"http://public.test/{i}": httpx.Response(
            302, headers={"location": f"http://public.test/{i + 1}"}
        )
        for i in range(10)
    }
    client = _transport(pages)
    with pytest.raises(FetchBlockedError, match="redirects"):
        _fetcher(client).fetch("http://public.test/0")


def test_size_limit_blocked():
    big = b"x" * (2_000_001)
    client = _transport({"http://public.test/big": httpx.Response(200, content=big)})
    with pytest.raises(FetchBlockedError, match="too large"):
        _fetcher(client, max_bytes=2_000_000).fetch("http://public.test/big")


def test_size_limit_stops_reading_stream_after_limit_is_exceeded():
    class CountingStream(httpx.SyncByteStream):
        def __init__(self):
            self.chunks_yielded = 0

        def __iter__(self):
            self.chunks_yielded += 1
            yield b"oversized"
            self.chunks_yielded += 1
            yield b"must-not-be-read"

    stream = CountingStream()
    client = _transport(
        {"http://public.test/big": httpx.Response(200, stream=stream)}
    )

    with pytest.raises(FetchBlockedError, match="too large"):
        _fetcher(client, max_bytes=4).fetch("http://public.test/big")

    assert stream.chunks_yielded == 1


def test_conditional_request_surfaces_validators():
    client = _transport(
        {"http://public.test/feed": httpx.Response(304, headers={"etag": '"v2"'})}
    )
    result = _fetcher(client).fetch("http://public.test/feed", etag='"v1"')
    assert result.status_code == 304
    assert result.etag == '"v2"'


def test_robots_disallow_blocked():
    client = _transport({})

    def robot_loader(base: str) -> str:
        return "User-agent: *\nDisallow: /private/\n"

    fetcher = SafeFetcher(
        client=client,
        respect_robots=True,
        min_host_interval=0.0,
        resolver=_fake_resolver({}),
        robot_loader=robot_loader,
    )
    with pytest.raises(FetchBlockedError, match="robots"):
        fetcher.fetch("http://public.test/private/doc")


def test_validate_url_bad_dns_fails_closed():
    def failing_resolver(host):
        from packages.research.fetcher import FetchBlockedError as F

        raise F("dns down")

    with pytest.raises(FetchBlockedError):
        validate_url("http://unresolvable.test/", failing_resolver)
