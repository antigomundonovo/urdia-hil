"""Source adapters (Doc 09): RSS, Atom, Sitemap, Search, GDELT, Wikidata,
Wikipedia, OpenAlex, Crossref, Wayback, Internet Archive, Wikimedia.

V1 implements RSS/Atom, Sitemap, Crossref and OpenAlex without new
dependencies. Remaining adapter types are declared by the spec and raise
AdapterError when invoked; they never fail silently.
"""

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

from packages.research.fetcher import FetchResult, SafeFetcher


class AdapterError(Exception):
    pass


@dataclass
class RawItem:
    url: str
    title: str | None = None
    summary: str | None = None
    published_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        """Content identity for clustering (Doc 09 dedup): title+summary only —
        the URL is handled by canonical-URL dedup, so copies at different
        locations hash equal. URL-less items hash by URL."""
        if not self.title and not self.summary:
            basis = {"url": self.url}
        else:
            basis = {"title": self.title, "summary": self.summary}
        return hashlib.sha256(
            json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()


class SourceAdapter(Protocol):
    source_type: str

    def fetch_items(self, source_url: str, fetcher: SafeFetcher) -> list[RawItem]: ...


# --- RSS / Atom (namespace-aware, stdlib) --------------------------------

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9",
}


def _require_success(result: FetchResult, source_type: str) -> None:
    if not 200 <= result.status_code < 300:
        raise AdapterError(f"{source_type} request returned HTTP {result.status_code}")


def _parse_xml(xml_bytes: bytes, source_type: str) -> ET.Element:
    if b"<!doctype" in xml_bytes.lower() or b"<!entity" in xml_bytes.lower():
        raise AdapterError(f"{source_type} XML declarations are not allowed")
    try:
        return ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise AdapterError(f"invalid {source_type} XML: {exc}") from exc


def _is_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and (port is None or port > 0)
        and parsed.username is None
        and parsed.password is None
    )


def _text(el: ET.Element | None) -> str | None:
    if el is None:
        return None
    return (el.text or "").strip() or None


def _parse_feed(xml_bytes: bytes, source_type: str = "rss") -> list[RawItem]:
    root = _parse_xml(xml_bytes, "feed")

    items: list[RawItem] = []
    # RSS 2.0
    for item in root.iter("item"):
        link = _text(item.find("link"))
        if not link or not _is_http_url(link):
            guid_el = item.find("guid")
            link = _text(guid_el)
        if not link or not _is_http_url(link):
            continue
        items.append(
            RawItem(
                url=link,
                title=_text(item.find("title")),
                summary=_text(item.find("description"))
                or _text(item.find(f"{{{_NS['content']}}}encoded")),
                published_at=_text(item.find("pubDate")),
                raw={"source": source_type},
            )
        )
    if items:
        return items
    # Atom
    for entry in root.iter(f"{{{_NS['atom']}}}entry"):
        link_el = entry.find(f"{{{_NS['atom']}}}link")
        href = link_el.get("href") if link_el is not None else None
        if not href or not _is_http_url(href):
            continue
        items.append(
            RawItem(
                url=href,
                title=_text(entry.find(f"{{{_NS['atom']}}}title")),
                summary=_text(entry.find(f"{{{_NS['atom']}}}summary"))
                or _text(entry.find(f"{{{_NS['atom']}}}content")),
                published_at=_text(entry.find(f"{{{_NS['atom']}}}published")),
                raw={"source": source_type},
            )
        )
    return items


class RssAdapter:
    source_type = "rss"

    def __init__(self, fetcher: SafeFetcher) -> None:
        self.fetcher = fetcher

    def fetch_items(self, source_url: str, fetcher: SafeFetcher | None = None) -> list[RawItem]:
        result = (fetcher or self.fetcher).fetch(source_url)
        _require_success(result, self.source_type)
        return _parse_feed(result.content, self.source_type)


class AtomAdapter(RssAdapter):
    source_type = "atom"


# --- sitemap and academic metadata adapters ------------------------------

_MAX_SITEMAP_DOCUMENTS = 20
_MAX_SITEMAP_ITEMS = 1000


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class SitemapAdapter:
    source_type = "sitemap"

    def __init__(self, fetcher: SafeFetcher) -> None:
        self.fetcher = fetcher

    def fetch_items(self, source_url: str, fetcher: SafeFetcher | None = None) -> list[RawItem]:
        active_fetcher = fetcher or self.fetcher
        pending = [source_url]
        visited: set[str] = set()
        items: list[RawItem] = []

        while pending:
            sitemap_url = pending.pop()
            if sitemap_url in visited:
                continue
            if len(visited) >= _MAX_SITEMAP_DOCUMENTS:
                raise AdapterError("sitemap index exceeds document limit")
            visited.add(sitemap_url)

            result = active_fetcher.fetch(sitemap_url)
            _require_success(result, self.source_type)
            root = _parse_xml(result.content, self.source_type)
            root_name = _local_name(root.tag)
            if root_name not in {"urlset", "sitemapindex"}:
                raise AdapterError("sitemap root must be urlset or sitemapindex")

            for entry in root:
                entry_name = _local_name(entry.tag)
                location = next(
                    (_text(child) for child in entry if _local_name(child.tag) == "loc"),
                    None,
                )
                if not location:
                    continue
                if not _is_http_url(location):
                    raise AdapterError("sitemap locations must be valid absolute HTTP(S) URLs")
                if root_name == "sitemapindex" and entry_name == "sitemap":
                    pending.append(location)
                    continue
                if root_name != "urlset" or entry_name != "url":
                    continue
                if len(items) >= _MAX_SITEMAP_ITEMS:
                    raise AdapterError("sitemap exceeds item limit")
                last_modified = next(
                    (_text(child) for child in entry if _local_name(child.tag) == "lastmod"),
                    None,
                )
                items.append(
                    RawItem(
                        url=location,
                        published_at=last_modified,
                        raw={"source": "sitemap"},
                    )
                )
        return items


def _parse_json_result(result: FetchResult, source_type: str) -> dict[str, Any]:
    _require_success(result, source_type)
    try:
        payload = json.loads(result.content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AdapterError(f"invalid {source_type} JSON response") from exc
    if not isinstance(payload, dict):
        raise AdapterError(f"{source_type} response must be a JSON object")
    return payload


def _first_text(value: Any) -> str | None:
    if isinstance(value, list):
        return next(
            (item.strip() for item in value if isinstance(item, str) and item.strip()),
            None,
        )
    return value.strip() if isinstance(value, str) and value.strip() else None


def _date_from_crossref(record: dict[str, Any]) -> str | None:
    for key in ("published-print", "published-online", "published"):
        date = record.get(key)
        parts = date.get("date-parts") if isinstance(date, dict) else None
        if parts and isinstance(parts[0], list) and parts[0]:
            if not all(type(part) is int and part >= 0 for part in parts[0]):
                continue
            return "-".join(
                f"{part:02d}" if index > 0 else str(part)
                for index, part in enumerate(parts[0])
            )
    return None


class CrossrefAdapter:
    source_type = "crossref"

    def __init__(self, fetcher: SafeFetcher) -> None:
        self.fetcher = fetcher

    def fetch_items(self, source_url: str, fetcher: SafeFetcher | None = None) -> list[RawItem]:
        result = (fetcher or self.fetcher).fetch(source_url)
        payload = _parse_json_result(result, self.source_type)
        message = payload.get("message")
        records = message.get("items") if isinstance(message, dict) else None
        if not isinstance(records, list):
            raise AdapterError("Crossref response is missing message.items")
        items: list[RawItem] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            doi = record.get("DOI")
            url = record.get("URL") or (
                f"https://doi.org/{doi}" if isinstance(doi, str) else None
            )
            if not isinstance(url, str) or not _is_http_url(url):
                continue
            abstract = record.get("abstract")
            summary = None
            if isinstance(abstract, str):
                try:
                    summary = " ".join(
                        _parse_xml(abstract.encode(), self.source_type).itertext()
                    ).strip()
                    summary = re.sub(r"\s+([,.;:!?])", r"\1", " ".join(summary.split()))
                except AdapterError:
                    summary = None
            items.append(
                RawItem(
                    url=url,
                    title=_first_text(record.get("title")),
                    summary=summary,
                    published_at=_date_from_crossref(record),
                    raw={
                        "source": self.source_type,
                        "doi": doi,
                        "publisher": record.get("publisher"),
                        "type": record.get("type"),
                    },
                )
            )
        return items


class OpenAlexAdapter:
    source_type = "openalex"

    def __init__(self, fetcher: SafeFetcher) -> None:
        self.fetcher = fetcher

    def fetch_items(self, source_url: str, fetcher: SafeFetcher | None = None) -> list[RawItem]:
        result = (fetcher or self.fetcher).fetch(source_url)
        payload = _parse_json_result(result, self.source_type)
        records = payload.get("results")
        if not isinstance(records, list):
            raise AdapterError("OpenAlex response is missing results")
        items: list[RawItem] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            location = record.get("primary_location")
            landing_page = location.get("landing_page_url") if isinstance(location, dict) else None
            doi = record.get("doi")
            url = landing_page or doi or record.get("id")
            if not isinstance(url, str) or not _is_http_url(url):
                continue
            abstract_index = record.get("abstract_inverted_index")
            summary = None
            if isinstance(abstract_index, dict):
                indexed_words = [
                    (position, word)
                    for word, positions in abstract_index.items()
                    if isinstance(word, str) and isinstance(positions, list)
                    for position in positions
                    if isinstance(position, int) and position >= 0
                ]
                if indexed_words:
                    summary = " ".join(
                        word for _, word in sorted(indexed_words, key=lambda item: item[0])
                    )
            items.append(
                RawItem(
                    url=url,
                    title=(
                        record.get("display_name")
                        if isinstance(record.get("display_name"), str)
                        else None
                    ),
                    summary=summary,
                    published_at=record.get("publication_date"),
                    raw={
                        "source": self.source_type,
                        "openalex_id": record.get("id"),
                        "doi": doi,
                        "type": record.get("type"),
                    },
                )
            )
        return items


# --- declared-but-not-yet-implemented adapters ---------------------------

_DECLARED_LATER = (
    "search",
    "gdelt",
    "wikidata",
    "wikipedia",
    "wayback",
    "internet_archive",
    "wikimedia",
)


class NotImplementedAdapter:
    """Declared by Doc 09, implemented in later milestones — fails loudly."""

    def __init__(self, source_type: str) -> None:
        self.source_type = source_type

    def fetch_items(self, source_url: str, fetcher: SafeFetcher | None = None) -> list[RawItem]:
        raise AdapterError(f"adapter '{self.source_type}' not implemented yet (Doc 09)")


def get_adapter(source_type: str, fetcher: SafeFetcher) -> SourceAdapter:
    if source_type == "rss":
        return RssAdapter(fetcher)
    if source_type == "atom":
        return AtomAdapter(fetcher)
    if source_type == "sitemap":
        return SitemapAdapter(fetcher)
    if source_type == "crossref":
        return CrossrefAdapter(fetcher)
    if source_type == "openalex":
        return OpenAlexAdapter(fetcher)
    if source_type in _DECLARED_LATER:
        return NotImplementedAdapter(source_type)
    raise AdapterError(f"unknown source_type: {source_type}")


def content_hash_of(result: FetchResult) -> str:
    return hashlib.sha256(result.content).hexdigest()
