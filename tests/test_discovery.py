"""Discovery engine tests (Doc 09): normalize, dedup, cluster, observability,
and RSS/Atom adapters against canned feeds — no real network."""

import uuid

import httpx
import pytest
from sqlalchemy import select

from packages.domain.models import (
    DiscoveryCluster,
    DiscoveryItem,
    Profile,
    Retrieval,
    Source,
    Workspace,
)
from packages.research.adapters import AdapterError, _parse_feed, get_adapter
from packages.research.discovery import DiscoveryEngine, canonicalize_url
from packages.research.fetcher import SafeFetcher

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Fonte Teste</title>
<item><title>Descoberta de 1920</title>
<link>http://arquivo.test/post-1?utm_source=x</link>
<description>Um achado.</description>
<pubDate>Tue, 29 Sep 2026 10:00:00 GMT</pubDate></item>
<item><title>Outro achado</title><link>http://arquivo.test/post-2</link><description>Outro.</description></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom achado</title><link href="http://arquivo.test/atom-1"/><summary>Resumo.</summary></entry>
</feed>"""


def _fetcher_for(pages: dict[str, bytes]) -> SafeFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        body = pages.get(str(request.url))
        return httpx.Response(200, content=body) if body is not None else httpx.Response(404)

    return SafeFetcher(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        respect_robots=False,
        min_host_interval=0.0,
        resolver=lambda host: ["93.184.216.34"],
    )


def test_canonicalize_url_strips_tracking_and_fragment():
    assert (
        canonicalize_url("https://Site.test/P%C3%A1gina?a=2&utm_source=x#top")
        == "https://site.test/P%C3%A1gina?a=2"
    )
    assert canonicalize_url("http://site.test:80/x") == "http://site.test/x"


def test_parse_feed_rss_and_atom():
    rss_items = _parse_feed(RSS)
    assert len(rss_items) == 2
    assert rss_items[0].url == "http://arquivo.test/post-1?utm_source=x"
    atom_items = _parse_feed(ATOM)
    assert len(atom_items) == 1
    assert atom_items[0].url == "http://arquivo.test/atom-1"


def test_unknown_and_unimplemented_adapters_fail_loudly():
    with pytest.raises(AdapterError):
        get_adapter("facebook", None)  # not in Doc 09 list
    adapter = get_adapter("wikidata", None)  # declared, not implemented yet
    with pytest.raises(AdapterError, match="not implemented"):
        adapter.fetch_items("http://x.test", None)


@pytest.fixture()
def world(db):
    ws = Workspace(name=f"disc-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    return ws, profile


def test_scan_creates_items_dedups_and_clusters(db, world):
    ws, profile = world
    source = Source(
        workspace_id=ws.id,
        profile_id=profile.id,
        url="http://public.test/feed",
        source_type="rss",
    )
    db.add(source)
    db.flush()

    engine = DiscoveryEngine(db, _fetcher_for({"http://public.test/feed": RSS}))
    report = engine.scan_source(source)
    assert report.status == "OK"
    assert report.items_seen == 2
    assert report.items_new == 2
    assert report.duplicates == 0

    # second scan: everything is a duplicate (dedup by canonical URL/hash)
    report2 = engine.scan_source(source)
    assert report2.items_new == 0
    assert report2.duplicates == 2

    # observability rows (Doc 09) — two retrievals, append-only history
    retrievals = list(db.scalars(select(Retrieval)).all())
    assert len(retrievals) == 2


def test_same_content_in_two_sources_clusters_not_duplicates(db, world):
    ws, profile = world
    s1 = Source(
        workspace_id=ws.id, profile_id=profile.id, url="http://a.test/feed", source_type="rss"
    )
    s2 = Source(
        workspace_id=ws.id, profile_id=profile.id, url="http://b.test/feed", source_type="rss"
    )
    db.add_all([s1, s2])
    db.flush()

    def feed_with(url: str) -> bytes:
        return (
            b'<?xml version="1.0"?><rss version="2.0"><channel><item>'
            b"<title>Historia compartilhada</title>"
            b"<link>" + url.encode() + b"</link>"
            b"<description>Texto identico.</description>"
            b"</item></channel></rss>"
        )

    engine = DiscoveryEngine(
        db,
        _fetcher_for(
            {
                "http://a.test/feed": feed_with("http://a.test/copy"),
                "http://b.test/feed": feed_with("http://b.test/copy"),
            }
        ),
    )
    engine.scan_source(s1)
    engine.scan_source(s2)

    clusters = list(db.scalars(select(DiscoveryCluster)).all())
    items = list(db.scalars(select(DiscoveryItem)).all())
    assert len(clusters) == 1  # one story, not two
    assert len(items) == 1  # the copy is a dependency, not a new item
    assert clusters[0].item_count == 2  # two source instances of one story


def test_fetch_blocked_source_records_failure(db, world):
    ws, profile = world
    source = Source(
        workspace_id=ws.id,
        profile_id=profile.id,
        url="http://localhost/feed",  # SSRF policy blocks even before network
        source_type="rss",
    )
    db.add(source)
    db.flush()
    engine = DiscoveryEngine(db, _fetcher_for({}))
    report = engine.scan_source(source)
    assert report.status == "FAILED"
    assert report.items_seen == 0
