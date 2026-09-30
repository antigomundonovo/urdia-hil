"""Source adapters (Doc 09): RSS, Atom, Sitemap, Search, GDELT, Wikidata,
Wikipedia, OpenAlex, Crossref, Wayback, Internet Archive, Wikimedia.

V1 implements RSS and Atom (stdlib XML parsing, no new dependencies); the
remaining adapter types are declared by the spec and raise AdapterError when
invoked — registering a source type without an implementation must fail
loudly, never silently.
"""

import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Protocol

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
}


def _text(el: ET.Element | None) -> str | None:
    if el is None:
        return None
    return (el.text or "").strip() or None


def _parse_feed(xml_bytes: bytes) -> list[RawItem]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise AdapterError(f"invalid feed XML: {exc}") from exc

    items: list[RawItem] = []
    # RSS 2.0
    for item in root.iter("item"):
        link = _text(item.find("link"))
        if not link:
            guid_el = item.find("guid")
            link = _text(guid_el)
        if not link:
            continue
        items.append(
            RawItem(
                url=link,
                title=_text(item.find("title")),
                summary=_text(item.find("description"))
                or _text(item.find(f"{{{_NS['content']}}}encoded")),
                published_at=_text(item.find("pubDate")),
                raw={"source": "rss"},
            )
        )
    if items:
        return items
    # Atom
    for entry in root.iter(f"{{{_NS['atom']}}}entry"):
        link_el = entry.find(f"{{{_NS['atom']}}}link")
        href = link_el.get("href") if link_el is not None else None
        if not href:
            continue
        items.append(
            RawItem(
                url=href,
                title=_text(entry.find(f"{{{_NS['atom']}}}title")),
                summary=_text(entry.find(f"{{{_NS['atom']}}}summary"))
                or _text(entry.find(f"{{{_NS['atom']}}}content")),
                published_at=_text(entry.find(f"{{{_NS['atom']}}}published")),
                raw={"source": "atom"},
            )
        )
    return items


class RssAdapter:
    source_type = "rss"

    def __init__(self, fetcher: SafeFetcher) -> None:
        self.fetcher = fetcher

    def fetch_items(self, source_url: str, fetcher: SafeFetcher | None = None) -> list[RawItem]:
        result = self.fetcher.fetch(source_url)
        return _parse_feed(result.content)


class AtomAdapter(RssAdapter):
    source_type = "atom"


# --- declared-but-not-yet-implemented adapters ---------------------------

_DECLARED_LATER = (
    "sitemap",
    "search",
    "gdelt",
    "wikidata",
    "wikipedia",
    "openalex",
    "crossref",
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
    if source_type in ("rss", "atom"):
        return RssAdapter(fetcher)
    if source_type in _DECLARED_LATER:
        return NotImplementedAdapter(source_type)
    raise AdapterError(f"unknown source_type: {source_type}")


def content_hash_of(result: FetchResult) -> str:
    return hashlib.sha256(result.content).hexdigest()
