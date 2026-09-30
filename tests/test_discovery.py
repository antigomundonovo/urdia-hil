"""Discovery engine tests (Doc 09): normalize, dedup, cluster, observability,
and RSS/Atom adapters against canned feeds — no real network."""

import json
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
    assert canonicalize_url("https://site.test:80/x") == "https://site.test:80/x"
    assert canonicalize_url("http://site.test:443/x") == "http://site.test:443/x"
    assert canonicalize_url("https://[2001:db8::1]:443/x") == "https://[2001:db8::1]/x"


def test_parse_feed_rss_and_atom():
    rss_items = _parse_feed(RSS)
    assert len(rss_items) == 2
    assert rss_items[0].url == "http://arquivo.test/post-1?utm_source=x"
    atom_items = _parse_feed(ATOM, "atom")
    assert len(atom_items) == 1
    assert atom_items[0].url == "http://arquivo.test/atom-1"
    assert atom_items[0].raw["source"] == "atom"


def test_unknown_and_unimplemented_adapters_fail_loudly():
    with pytest.raises(AdapterError):
        get_adapter("facebook", None)  # not in Doc 09 list
    adapter = get_adapter("wikidata", None)  # declared, not implemented yet
    with pytest.raises(AdapterError, match="not implemented"):
        adapter.fetch_items("http://x.test", None)


def test_sitemap_adapter_reads_urlsets_and_indexes():
    from packages.research.adapters import SitemapAdapter

    index_url = "http://public.test/sitemap.xml"
    child_url = "http://public.test/child.xml"
    fetcher = _fetcher_for(
        {
            index_url: b"""<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <sitemap><loc>http://public.test/child.xml</loc></sitemap>
            </sitemapindex>""",
            child_url: b"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url><loc>https://museum.test/item/1</loc><lastmod>2026-09-30</lastmod></url>
              <url><loc>https://museum.test/item/2</loc></url>
            </urlset>""",
        }
    )

    items = SitemapAdapter(fetcher).fetch_items(index_url)

    assert [(item.url, item.published_at) for item in items] == [
        ("https://museum.test/item/1", "2026-09-30"),
        ("https://museum.test/item/2", None),
    ]
    assert all(item.raw == {"source": "sitemap"} for item in items)


def test_sitemap_adapter_rejects_dtd_and_invalid_locations():
    from packages.research.adapters import SitemapAdapter

    dtd_fetcher = _fetcher_for(
        {
            "http://public.test/sitemap.xml": b"""<!DOCTYPE foo [<!ENTITY x "boom">]>
              <urlset><url><loc>https://museum.test/&x;</loc></url></urlset>"""
        }
    )
    with pytest.raises(AdapterError, match="declarations are not allowed"):
        SitemapAdapter(dtd_fetcher).fetch_items("http://public.test/sitemap.xml")

    invalid_location_fetcher = _fetcher_for(
        {
            "http://public.test/sitemap.xml": b"""<urlset>
              <url><loc>file:///private/data</loc></url></urlset>"""
        }
    )
    with pytest.raises(AdapterError, match="valid absolute HTTP"):
        SitemapAdapter(invalid_location_fetcher).fetch_items(
            "http://public.test/sitemap.xml"
        )


def test_sitemap_adapter_wraps_malformed_location_urls():
    from packages.research.adapters import SitemapAdapter

    fetcher = _fetcher_for(
        {
            "http://public.test/sitemap.xml": b"""<urlset>
              <url><loc>https://[broken/item</loc></url></urlset>"""
        }
    )
    with pytest.raises(AdapterError, match="valid absolute HTTP"):
        SitemapAdapter(fetcher).fetch_items("http://public.test/sitemap.xml")


def test_academic_adapters_normalize_crossref_and_openalex_results():
    from packages.research.adapters import CrossrefAdapter, OpenAlexAdapter

    crossref_url = "http://public.test/crossref"
    openalex_url = "http://public.test/openalex"
    fetcher = _fetcher_for(
        {
            crossref_url: json.dumps(
                {
                    "message": {
                        "items": [
                            {
                                "DOI": "10.1234/history",
                                "title": ["História urbana"],
                                "published": {"date-parts": [[1911, 2, 3]]},
                                "abstract": (
                                    "<jats:p xmlns:jats='http://www.w3.org/1999/xhtml'>"
                                    "Documento <jats:italic>histórico</jats:italic>.</jats:p>"
                                ),
                                "publisher": "Arquivo Acadêmico",
                                "type": "article-journal",
                            }
                        ]
                    }
                }
            ).encode(),
            openalex_url: json.dumps(
                {
                    "results": [
                        {
                            "id": "https://openalex.org/W1",
                            "doi": "https://doi.org/10.1234/work",
                            "display_name": "Estudo documental",
                            "publication_date": "2024-05-01",
                            "primary_location": {
                                "landing_page_url": "https://journal.test/article"
                            },
                            "abstract_inverted_index": {
                                "Fonte": [0],
                                "primária": [1],
                                "relevante": [2],
                            },
                        }
                    ]
                }
            ).encode(),
        }
    )

    crossref = CrossrefAdapter(fetcher).fetch_items(crossref_url)
    openalex = OpenAlexAdapter(fetcher).fetch_items(openalex_url)

    assert crossref[0].url == "https://doi.org/10.1234/history"
    assert crossref[0].title == "História urbana"
    assert crossref[0].summary == "Documento histórico."
    assert crossref[0].published_at == "1911-02-03"
    assert crossref[0].raw["publisher"] == "Arquivo Acadêmico"
    assert openalex[0].url == "https://journal.test/article"
    assert openalex[0].summary == "Fonte primária relevante"
    assert openalex[0].published_at == "2024-05-01"


def test_openalex_adapter_handles_sparse_abstract_index():
    from packages.research.adapters import OpenAlexAdapter

    url = "http://public.test/openalex"
    fetcher = _fetcher_for(
        {
            url: json.dumps(
                {
                    "results": [
                        {
                            "id": "https://openalex.org/W2",
                            "abstract_inverted_index": {"contexto": [0], "histórico": [2]},
                        }
                    ]
                }
            ).encode()
        }
    )
    item = OpenAlexAdapter(fetcher).fetch_items(url)[0]
    assert item.summary == "contexto histórico"


def test_adapters_fail_loudly_on_http_errors():
    from packages.research.adapters import CrossrefAdapter, RssAdapter

    fetcher = _fetcher_for({})
    with pytest.raises(AdapterError, match="HTTP 404"):
        RssAdapter(fetcher).fetch_items("http://public.test/missing")
    with pytest.raises(AdapterError, match="HTTP 404"):
        CrossrefAdapter(fetcher).fetch_items("http://public.test/missing")


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

    # observability rows (Doc 09) — two retrievals for this workspace
    retrievals = list(
        db.scalars(select(Retrieval).where(Retrieval.workspace_id == ws.id))
    )
    assert len(retrievals) == 2


def test_scan_uses_persisted_http_validators_and_records_not_modified(db, world):
    ws, profile = world
    source = Source(
        workspace_id=ws.id,
        profile_id=profile.id,
        url="http://public.test/conditional-feed",
        source_type="rss",
    )
    db.add(source)
    db.flush()
    request_headers: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_headers.append(request.headers)
        if request.headers.get("if-none-match") == '"feed-v1"':
            return httpx.Response(304)
        return httpx.Response(
            200,
            content=RSS,
            headers={
                "etag": '"feed-v1"',
                "last-modified": "Tue, 29 Sep 2026 10:00:00 GMT",
            },
        )

    fetcher = SafeFetcher(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        respect_robots=False,
        min_host_interval=0.0,
        resolver=lambda host: ["93.184.216.34"],
    )
    engine = DiscoveryEngine(db, fetcher)

    first = engine.scan_source(source)
    db.flush()
    second = engine.scan_source(source)
    db.flush()
    retrievals = list(
        db.scalars(
            select(Retrieval)
            .where(Retrieval.source_id == source.id)
            .order_by(Retrieval.created_at, Retrieval.id)
        )
    )

    assert first.status == "OK"
    assert first.items_new == 2
    assert second.status == "NOT_MODIFIED"
    assert second.items_seen == second.items_new == second.duplicates == 0
    assert request_headers[1]["if-none-match"] == '"feed-v1"'
    assert request_headers[1]["if-modified-since"] == "Tue, 29 Sep 2026 10:00:00 GMT"
    successful = next(retrieval for retrieval in retrievals if retrieval.status == "OK")
    not_modified = next(
        retrieval for retrieval in retrievals if retrieval.status == "NOT_MODIFIED"
    )
    assert successful.http_status == 200
    assert not_modified.http_status == 304
    assert all(retrieval.etag == '"feed-v1"' for retrieval in retrievals)
    assert all(
        retrieval.last_modified == "Tue, 29 Sep 2026 10:00:00 GMT"
        for retrieval in retrievals
    )
    assert successful.content_hash == not_modified.content_hash


def test_scan_records_http_failures_without_losing_source_state(db, world):
    ws, profile = world
    source = Source(
        workspace_id=ws.id,
        profile_id=profile.id,
        url="http://public.test/unavailable-feed",
        source_type="rss",
    )
    db.add(source)
    db.flush()
    fetcher = SafeFetcher(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(503, content=b"temporarily unavailable")
            )
        ),
        respect_robots=False,
        min_host_interval=0.0,
        resolver=lambda host: ["93.184.216.34"],
    )

    report = DiscoveryEngine(db, fetcher).scan_source(source)
    retrieval = db.scalar(select(Retrieval).where(Retrieval.source_id == source.id))

    assert report.status == "FAILED"
    assert "HTTP 503" in report.error
    assert retrieval.status == "FAILED"
    assert retrieval.http_status == 503
    assert source.last_seen_at is None


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

    clusters = list(
        db.scalars(select(DiscoveryCluster).where(DiscoveryCluster.workspace_id == ws.id))
    )
    items = list(
        db.scalars(select(DiscoveryItem).where(DiscoveryItem.workspace_id == ws.id))
    )
    assert len(clusters) == 1  # one story, not two
    assert len(items) == 1  # the copy is a dependency, not a new item
    assert clusters[0].item_count == 2  # two source instances of one story


def test_discovery_deduplication_does_not_cross_profile_boundaries(db, world):
    ws, profile = world
    other_profile = Profile(
        workspace_id=ws.id,
        key="another",
        name="Another profile",
    )
    db.add(other_profile)
    db.flush()
    sources = [
        Source(
            workspace_id=ws.id,
            profile_id=profile.id,
            url="http://a.test/feed",
            source_type="rss",
        ),
        Source(
            workspace_id=ws.id,
            profile_id=other_profile.id,
            url="http://b.test/feed",
            source_type="rss",
        ),
    ]
    db.add_all(sources)
    db.flush()

    def feed_with(url: str) -> bytes:
        return (
            b'<?xml version="1.0"?><rss version="2.0"><channel><item>'
            b"<title>Shared topic</title><link>"
            + url.encode()
            + b"</link><description>Identical summary.</description>"
            b"</item></channel></rss>"
        )

    engine = DiscoveryEngine(
        db,
        _fetcher_for(
            {
                "http://a.test/feed": feed_with("http://a.test/story"),
                "http://b.test/feed": feed_with("http://b.test/story"),
            }
        ),
    )

    assert engine.scan_source(sources[0]).items_new == 1
    assert engine.scan_source(sources[1]).items_new == 1
    items = list(
        db.scalars(
            select(DiscoveryItem)
            .where(DiscoveryItem.workspace_id == ws.id)
            .order_by(DiscoveryItem.profile_id)
        )
    )
    clusters = list(
        db.scalars(
            select(DiscoveryCluster).where(DiscoveryCluster.workspace_id == ws.id)
        )
    )

    assert {item.profile_id for item in items} == {profile.id, other_profile.id}
    assert len(clusters) == 2
    assert {cluster.item_count for cluster in clusters} == {1}


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
