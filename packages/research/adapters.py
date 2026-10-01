"""Source adapters (Doc 09); source catalogs return leads, never evidence."""

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import quote, urlparse

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
    last_result: FetchResult | None

    def fetch_items(
        self,
        source_url: str,
        fetcher: SafeFetcher | None = None,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> list[RawItem]: ...


class _FetchingAdapter:
    def __init__(self, fetcher: SafeFetcher) -> None:
        self.fetcher = fetcher
        self.last_result: FetchResult | None = None

    def _fetch(
        self,
        source_url: str,
        fetcher: SafeFetcher | None,
        *,
        etag: str | None,
        last_modified: str | None,
    ) -> FetchResult:
        self.last_result = (fetcher or self.fetcher).fetch(
            source_url, etag=etag, last_modified=last_modified
        )
        return self.last_result


# --- RSS / Atom (namespace-aware, stdlib) --------------------------------

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9",
}


def _require_success(result: FetchResult, source_type: str) -> None:
    if result.status_code != 304 and not 200 <= result.status_code < 300:
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


class RssAdapter(_FetchingAdapter):
    source_type = "rss"

    def fetch_items(
        self,
        source_url: str,
        fetcher: SafeFetcher | None = None,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> list[RawItem]:
        result = self._fetch(
            source_url, fetcher, etag=etag, last_modified=last_modified
        )
        _require_success(result, self.source_type)
        if result.status_code == 304:
            return []
        return _parse_feed(result.content, self.source_type)


class AtomAdapter(RssAdapter):
    source_type = "atom"


# --- sitemap and academic metadata adapters ------------------------------

_MAX_SITEMAP_DOCUMENTS = 20
_MAX_SITEMAP_ITEMS = 1000


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class SitemapAdapter(_FetchingAdapter):
    source_type = "sitemap"

    def fetch_items(
        self,
        source_url: str,
        fetcher: SafeFetcher | None = None,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> list[RawItem]:
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

            if sitemap_url == source_url:
                result = self._fetch(
                    sitemap_url,
                    active_fetcher,
                    etag=etag,
                    last_modified=last_modified,
                )
            else:
                result = active_fetcher.fetch(sitemap_url)
            _require_success(result, self.source_type)
            if result.status_code == 304:
                return []
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


class _TextExtractor(HTMLParser):
    _BLOCK_TAGS = frozenset({"br", "div", "li", "p"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    extractor = _TextExtractor()
    extractor.feed(value)
    extractor.close()
    text = " ".join("".join(extractor.parts).split())
    return text or None


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


class CrossrefAdapter(_FetchingAdapter):
    source_type = "crossref"

    def fetch_items(
        self,
        source_url: str,
        fetcher: SafeFetcher | None = None,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> list[RawItem]:
        result = self._fetch(
            source_url, fetcher, etag=etag, last_modified=last_modified
        )
        if result.status_code == 304:
            return []
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


class OpenAlexAdapter(_FetchingAdapter):
    source_type = "openalex"

    def fetch_items(
        self,
        source_url: str,
        fetcher: SafeFetcher | None = None,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> list[RawItem]:
        result = self._fetch(
            source_url, fetcher, etag=etag, last_modified=last_modified
        )
        if result.status_code == 304:
            return []
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


class GdeltAdapter(_FetchingAdapter):
    source_type = "gdelt"

    def fetch_items(
        self,
        source_url: str,
        fetcher: SafeFetcher | None = None,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> list[RawItem]:
        result = self._fetch(
            source_url, fetcher, etag=etag, last_modified=last_modified
        )
        if result.status_code == 304:
            return []
        payload = _parse_json_result(result, self.source_type)
        records = payload.get("articles")
        if not isinstance(records, list):
            raise AdapterError("GDELT response is missing articles")
        items: list[RawItem] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            url = record.get("url")
            if not isinstance(url, str) or not _is_http_url(url):
                continue
            items.append(
                RawItem(
                    url=url,
                    title=record.get("title") if isinstance(record.get("title"), str) else None,
                    published_at=(
                        record.get("seendate")
                        if isinstance(record.get("seendate"), str)
                        else None
                    ),
                    raw={
                        "source": self.source_type,
                        "domain": record.get("domain"),
                        "language": record.get("language"),
                        "source_country": record.get("sourcecountry"),
                    },
                )
            )
        return items


class WikipediaAdapter(_FetchingAdapter):
    source_type = "wikipedia"

    def fetch_items(
        self,
        source_url: str,
        fetcher: SafeFetcher | None = None,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> list[RawItem]:
        result = self._fetch(
            source_url, fetcher, etag=etag, last_modified=last_modified
        )
        if result.status_code == 304:
            return []
        payload = _parse_json_result(result, self.source_type)
        query = payload.get("query")
        pages = query.get("pages") if isinstance(query, dict) else None
        if isinstance(pages, dict):
            records = list(pages.values())
        elif isinstance(pages, list):
            records = pages
        else:
            raise AdapterError("Wikipedia response is missing query.pages")
        items: list[RawItem] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            url = record.get("fullurl")
            if not isinstance(url, str) or not _is_http_url(url):
                continue
            items.append(
                RawItem(
                    url=url,
                    title=record.get("title") if isinstance(record.get("title"), str) else None,
                    summary=(
                        record.get("extract")
                        if isinstance(record.get("extract"), str)
                        else None
                    ),
                    published_at=(
                        record.get("timestamp")
                        if isinstance(record.get("timestamp"), str)
                        else None
                    ),
                    raw={"source": self.source_type, "page_id": record.get("pageid")},
                )
            )
        return items


class WikidataAdapter(_FetchingAdapter):
    source_type = "wikidata"

    def fetch_items(
        self,
        source_url: str,
        fetcher: SafeFetcher | None = None,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> list[RawItem]:
        result = self._fetch(
            source_url, fetcher, etag=etag, last_modified=last_modified
        )
        if result.status_code == 304:
            return []
        payload = _parse_json_result(result, self.source_type)
        records = payload.get("search")
        if not isinstance(records, list):
            raise AdapterError("Wikidata response is missing search results")
        items: list[RawItem] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            entity_id = record.get("id")
            if not isinstance(entity_id, str) or not re.fullmatch(r"Q[1-9]\d*", entity_id):
                continue
            items.append(
                RawItem(
                    url=f"https://www.wikidata.org/wiki/{entity_id}",
                    title=record.get("label") if isinstance(record.get("label"), str) else None,
                    summary=(
                        record.get("description")
                        if isinstance(record.get("description"), str)
                        else None
                    ),
                    raw={"source": self.source_type, "entity_id": entity_id},
                )
            )
        return items


class WaybackAdapter(_FetchingAdapter):
    source_type = "wayback"

    def fetch_items(
        self,
        source_url: str,
        fetcher: SafeFetcher | None = None,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> list[RawItem]:
        result = self._fetch(
            source_url, fetcher, etag=etag, last_modified=last_modified
        )
        if result.status_code == 304:
            return []
        _require_success(result, self.source_type)
        try:
            rows = json.loads(result.content)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AdapterError("invalid Wayback CDX JSON response") from exc
        if not isinstance(rows, list):
            raise AdapterError("Wayback CDX response must be a JSON array")
        if not rows:
            return []
        if not isinstance(rows[0], list) or "timestamp" not in rows[0]:
            raise AdapterError("Wayback CDX response is missing its field header")
        fields = rows[0]
        if any(not isinstance(field, str) for field in fields):
            raise AdapterError("Wayback CDX field header is invalid")
        items: list[RawItem] = []
        for row in rows[1:]:
            if not isinstance(row, list) or len(row) != len(fields):
                continue
            capture = dict(zip(fields, row, strict=True))
            original = capture.get("original")
            timestamp = capture.get("timestamp")
            if (
                not isinstance(original, str)
                or not _is_http_url(original)
                or not isinstance(timestamp, str)
                or not re.fullmatch(r"\d{14}", timestamp)
            ):
                continue
            try:
                datetime.strptime(timestamp, "%Y%m%d%H%M%S")
            except ValueError:
                continue
            archived_url = f"https://web.archive.org/web/{timestamp}id_/{original}"
            items.append(
                RawItem(
                    url=archived_url,
                    title=original,
                    published_at=timestamp,
                    raw={
                        "source": self.source_type,
                        "original_url": original,
                        "timestamp": timestamp,
                        "status_code": capture.get("statuscode"),
                        "mime_type": capture.get("mimetype"),
                        "digest": capture.get("digest"),
                    },
                )
            )
        return items


class InternetArchiveAdapter(_FetchingAdapter):
    source_type = "internet_archive"

    def fetch_items(
        self,
        source_url: str,
        fetcher: SafeFetcher | None = None,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> list[RawItem]:
        result = self._fetch(
            source_url, fetcher, etag=etag, last_modified=last_modified
        )
        if result.status_code == 304:
            return []
        payload = _parse_json_result(result, self.source_type)
        response = payload.get("response")
        records = response.get("docs") if isinstance(response, dict) else None
        if not isinstance(records, list):
            raise AdapterError("Internet Archive response is missing response.docs")
        items: list[RawItem] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            identifier = record.get("identifier")
            if (
                not isinstance(identifier, str)
                or not identifier
                or len(identifier) > 255
                or not re.fullmatch(r"[A-Za-z0-9._-]+", identifier)
            ):
                continue
            items.append(
                RawItem(
                    url=f"https://archive.org/details/{quote(identifier, safe='')}",
                    title=_first_text(record.get("title")),
                    summary=_plain_text(_first_text(record.get("description"))),
                    published_at=(
                        record.get("date") if isinstance(record.get("date"), str) else None
                    ),
                    raw={
                        "source": self.source_type,
                        "identifier": identifier,
                        "mediatype": record.get("mediatype"),
                        "creator": record.get("creator"),
                    },
                )
            )
        return items


class WikimediaAdapter(_FetchingAdapter):
    source_type = "wikimedia"

    def fetch_items(
        self,
        source_url: str,
        fetcher: SafeFetcher | None = None,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> list[RawItem]:
        result = self._fetch(
            source_url, fetcher, etag=etag, last_modified=last_modified
        )
        if result.status_code == 304:
            return []
        payload = _parse_json_result(result, self.source_type)
        query = payload.get("query")
        pages = query.get("pages") if isinstance(query, dict) else None
        if isinstance(pages, dict):
            records = list(pages.values())
        elif isinstance(pages, list):
            records = pages
        else:
            raise AdapterError("Wikimedia response is missing query.pages")
        items: list[RawItem] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            page_url = record.get("canonicalurl")
            if not isinstance(page_url, str) or not _is_http_url(page_url):
                continue
            image_info = record.get("imageinfo")
            image = image_info[0] if isinstance(image_info, list) and image_info else {}
            if not isinstance(image, dict):
                image = {}
            metadata = image.get("extmetadata")
            if not isinstance(metadata, dict):
                metadata = {}
            items.append(
                RawItem(
                    url=page_url,
                    title=record.get("title") if isinstance(record.get("title"), str) else None,
                    summary=_plain_text(
                        metadata.get("ImageDescription", {}).get("value")
                        if isinstance(metadata.get("ImageDescription"), dict)
                        else None
                    ),
                    raw={
                        "source": self.source_type,
                        "page_id": record.get("pageid"),
                        "file_url": image.get("url"),
                        "creator": _plain_text(
                            metadata.get("Artist", {}).get("value")
                            if isinstance(metadata.get("Artist"), dict)
                            else None
                        ),
                        "license": _plain_text(
                            metadata.get("LicenseShortName", {}).get("value")
                            if isinstance(metadata.get("LicenseShortName"), dict)
                            else None
                        ),
                        "license_url": _plain_text(
                            metadata.get("LicenseUrl", {}).get("value")
                            if isinstance(metadata.get("LicenseUrl"), dict)
                            else None
                        ),
                    },
                )
            )
        return items


# --- declared-but-not-yet-implemented adapters ---------------------------

_DECLARED_LATER = (
    "search",
)

SUPPORTED_SOURCE_TYPES = frozenset(
    {
        "rss",
        "atom",
        "sitemap",
        "crossref",
        "openalex",
        "gdelt",
        "wikipedia",
        "wikidata",
        "wayback",
        "internet_archive",
        "wikimedia",
    }
)


class NotImplementedAdapter:
    """Declared by Doc 09, implemented in later milestones — fails loudly."""

    def __init__(self, source_type: str) -> None:
        self.source_type = source_type
        self.last_result: FetchResult | None = None

    def fetch_items(
        self,
        source_url: str,
        fetcher: SafeFetcher | None = None,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> list[RawItem]:
        raise AdapterError(f"adapter '{self.source_type}' not implemented yet (Doc 09)")


def _vtt_to_text(vtt: str) -> str:
    """Flatten a WebVTT caption file to plain transcript text (no cues/
    timestamps/headers). Igna apenas conteúdo legível (Doc 09 normalize)."""
    lines: list[str] = []
    seen: set[str] = set()
    for line in vtt.splitlines():
        line = line.strip()
        if (
            not line
            or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))
            or "-->" in line
            or line.isdigit()
        ):
            continue
        line = re.sub(r"<[^>]+>", "", line)  # strip inline tags
        if line and line not in seen:
            seen.add(line)
            lines.append(line)
    return " ".join(lines)


class YouTubeAdapter:
    """YouTube source adapter (AMENDMENT-012 approved, Doc 09 provenance).

    Metadata + captions only — never downloads video bytes. Single video URLs
    produce one RawItem whose summary is the best available pt-BR (or any)
    transcript; channel/playlist URLs produce metadata-only items for the
    latest entries. yt-dlp does its own networking (SafeFetcher not used for
    the fetch itself); everything extracted is untrusted data (Doc 08).
    """

    source_type = "youtube"

    _BASE_YDL_OPTS = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": False,
    }

    def __init__(self, fetcher: SafeFetcher) -> None:
        self.fetcher = fetcher
        self.last_result: FetchResult | None = None

    @staticmethod
    def _ydl_opts() -> dict[str, Any]:
        """Base options; YouTube now requires a session for metadata — cookies
        come from the operator's own browser (optional settings, local only)."""
        from packages.shared.settings import get_settings

        opts = dict(YouTubeAdapter._BASE_YDL_OPTS)
        settings = get_settings()
        if settings.yt_dlp_cookies_from_browser:
            opts["cookiesfrombrowser"] = (
                settings.yt_dlp_cookies_from_browser,
            )
        elif settings.yt_dlp_cookies_file:
            opts["cookiefile"] = settings.yt_dlp_cookies_file
        return opts

    def fetch_items(
        self,
        source_url: str,
        fetcher: SafeFetcher | None = None,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> list[RawItem]:
        try:
            import yt_dlp
        except ImportError as exc:  # pragma: no cover - declared dependency
            raise AdapterError("yt-dlp is not installed") from exc

        try:
            with yt_dlp.YoutubeDL(self._ydl_opts()) as ydl:
                info = ydl.extract_info(source_url, download=False)
        except Exception as exc:
            raise AdapterError(f"youtube fetch failed: {exc.__class__.__name__}") from exc
        if not info:
            return []

        if info.get("_type") == "playlist" or "entries" in info:
            items = []
            for entry in (info.get("entries") or [])[:25]:
                if not entry or not entry.get("id"):
                    continue
                url = entry.get("url") or (
                    f"https://www.youtube.com/watch?v={entry['id']}"
                )
                items.append(
                    RawItem(
                        url=url,
                        title=entry.get("title"),
                        summary=(entry.get("description") or "").strip() or None,
                        published_at=_youtube_date(entry.get("upload_date")),
                    )
                )
            return items

        return [self._video_item(info)]

    def _video_item(self, info: dict[str, Any]) -> RawItem:
        transcript = self._best_transcript(info)
        summary = transcript or (info.get("description") or "").strip() or None
        return RawItem(
            url=info.get("webpage_url")
            or f"https://www.youtube.com/watch?v={info.get('id', '')}",
            title=info.get("title"),
            summary=summary,
            published_at=_youtube_date(info.get("upload_date")),
        )

    def _best_transcript(self, info: dict[str, Any]) -> str | None:
        """Manual captions first (pt-BR → pt → en → any), then auto captions."""
        for tracks in (info.get("subtitles"), info.get("automatic_captions")):
            if not tracks:
                continue
            for lang in ("pt-BR", "pt", "en"):
                candidates = [k for k in tracks if k.startswith(lang)]
                chosen = (candidates or list(tracks))[:1]
                for key in chosen:
                    for fmt in tracks[key]:
                        if fmt.get("ext") in ("vtt", "srv3", "json3") or fmt.get("url"):
                            text = self._fetch_caption(fmt.get("url"))
                            if text:
                                return text
        return None

    def _fetch_caption(self, url: str | None) -> str | None:
        if not url:
            return None
        try:
            result = self.fetcher.fetch(url)
        except Exception:
            return None
        if result.status_code != 200 or not result.content:
            return None
        try:
            text = _vtt_to_text(result.content.decode("utf-8", errors="replace"))
        except Exception:
            return None
        return text or None


def _youtube_date(upload_date: str | None) -> str | None:
    if upload_date and len(upload_date) == 8:
        return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
    return upload_date


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
    if source_type == "gdelt":
        return GdeltAdapter(fetcher)
    if source_type == "wikipedia":
        return WikipediaAdapter(fetcher)
    if source_type == "wikidata":
        return WikidataAdapter(fetcher)
    if source_type == "wayback":
        return WaybackAdapter(fetcher)
    if source_type == "internet_archive":
        return InternetArchiveAdapter(fetcher)
    if source_type == "wikimedia":
        return WikimediaAdapter(fetcher)
    if source_type == "youtube":
        return YouTubeAdapter(fetcher)
    if source_type in _DECLARED_LATER:
        return NotImplementedAdapter(source_type)
    raise AdapterError(f"unknown source_type: {source_type}")


def content_hash_of(result: FetchResult) -> str:
    return hashlib.sha256(result.content).hexdigest()
