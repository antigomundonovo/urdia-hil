"""Discovery engine (Doc 09).

Pipeline: source config → fetch → normalize → deduplicate → candidate items
→ cluster → observability. Search results are LEADS, never evidence (Doc 09
"Search is not evidence") — items carry status NORMALIZED/CLUSTERED and wait
for the research/evidence milestones.

Dedup uses canonical URL normalization + content hash (Doc 09). Clustering
groups items sharing a content hash into one cluster — dependency analysis
(source_relations) records that copies are NOT independent confirmations.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.models import DiscoveryCluster, DiscoveryItem, Retrieval, Source
from packages.research.adapters import AdapterError, RawItem, get_adapter
from packages.research.fetcher import FetchBlockedError, SafeFetcher

logger = logging.getLogger(__name__)

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "ref", "source",
}


def canonicalize_url(url: str) -> str:
    """URL normalization (Doc 09): lowercase host, drop fragment and tracking
    params, sort remaining query params."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    scheme = parsed.scheme.lower()
    pairs = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    pairs.sort()
    query = urlencode(pairs)
    port = parsed.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    return urlunparse((scheme, netloc, parsed.path or "/", "", query, ""))


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class ScanReport:
    source_id: Any
    items_seen: int = 0
    items_new: int = 0
    duplicates: int = 0
    status: str = "OK"
    error: str | None = None
    duration_ms: int = 0


class DiscoveryEngine:
    def __init__(self, session: Session, fetcher: SafeFetcher) -> None:
        self.session = session
        self.fetcher = fetcher

    def active_sources(self, workspace_id, profile_id) -> list[Source]:
        return list(
            self.session.scalars(
                select(Source).where(
                    Source.workspace_id == workspace_id,
                    Source.profile_id == profile_id,
                    Source.status == "ACTIVE",
                )
            )
        )

    def _existing_hashes(self, workspace_id) -> set[str]:
        rows = self.session.scalars(
            select(DiscoveryItem.content_hash).where(
                DiscoveryItem.workspace_id == workspace_id,
                DiscoveryItem.content_hash.is_not(None),
            )
        )
        return set(rows)

    def _existing_urls(self, workspace_id) -> set[str]:
        rows = self.session.scalars(
            select(DiscoveryItem.url).where(
                DiscoveryItem.workspace_id == workspace_id,
                DiscoveryItem.url.is_not(None),
            )
        )
        return {canonicalize_url(u) for u in rows}

    def scan_source(self, source: Source) -> ScanReport:
        started = datetime.now(UTC)
        report = ScanReport(source_id=source.id)
        retrieval = Retrieval(
            workspace_id=source.workspace_id,
            profile_id=source.profile_id,
            source_id=source.id,
            status="RUNNING",
        )
        self.session.add(retrieval)
        try:
            adapter = get_adapter(source.source_type, self.fetcher)
            items: list[RawItem] = adapter.fetch_items(source.url)
        except (FetchBlockedError, AdapterError) as exc:
            report.status = "FAILED"
            report.error = str(exc)
            retrieval.status = "FAILED"
            retrieval.error = str(exc)
            self._finish(retrieval, report, started)
            return report

        report.items_seen = len(items)
        seen_hashes = self._existing_hashes(source.workspace_id)
        seen_urls = self._existing_urls(source.workspace_id)

        for item in items:
            canon = canonicalize_url(item.url)
            chash = item.content_hash
            if canon in seen_urls or chash in seen_hashes:
                report.duplicates += 1
                # A copy at a DIFFERENT url is a source dependency (Doc 09):
                # record it on the cluster without creating a new item.
                if canon not in seen_urls:
                    self._count_dependency(source, chash)
                continue
            cluster = self._cluster_for(source, item, chash)
            entry = DiscoveryItem(
                workspace_id=source.workspace_id,
                profile_id=source.profile_id,
                source_id=source.id,
                cluster_id=cluster.id,
                url=item.url,
                title=item.title,
                summary=item.summary,
                content_hash=chash,
                raw=item.raw,
                status=(
                    "CLUSTERED" if cluster.item_count and cluster.item_count > 1 else "NORMALIZED"
                ),
            )
            self.session.add(entry)
            seen_urls.add(canon)
            seen_hashes.add(chash)
            report.items_new += 1

        source.last_seen_at = datetime.now(UTC)
        retrieval.status = "OK"
        retrieval.item_count = report.items_new
        self._finish(retrieval, report, started)
        return report

    def _count_dependency(self, source: Source, chash: str) -> None:
        existing = self.session.scalars(
            select(DiscoveryItem)
            .where(
                DiscoveryItem.workspace_id == source.workspace_id,
                DiscoveryItem.content_hash == chash,
            )
            .limit(1)
        ).first()
        if existing is not None and existing.cluster_id is not None:
            cluster = self.session.get(DiscoveryCluster, existing.cluster_id)
            if cluster is not None:
                cluster.item_count = (cluster.item_count or 1) + 1
                self.session.flush()

    def _cluster_for(self, source: Source, item: RawItem, chash: str) -> DiscoveryCluster:
        """Same content hash → same cluster (Doc 09: source dependency — a
        copy is not a new story nor independent confirmation)."""
        existing = self.session.scalars(
            select(DiscoveryItem)
            .where(
                DiscoveryItem.workspace_id == source.workspace_id,
                DiscoveryItem.content_hash == chash,
            )
            .limit(1)
        ).first()
        if existing is not None and existing.cluster_id is not None:
            cluster = self.session.get(DiscoveryCluster, existing.cluster_id)
            if cluster is not None:
                cluster.item_count = (cluster.item_count or 1) + 1
                self.session.flush()
                return cluster
        cluster = DiscoveryCluster(
            workspace_id=source.workspace_id,
            profile_id=source.profile_id,
            label=item.title,
            item_count=1,
        )
        self.session.add(cluster)
        self.session.flush()
        return cluster

    def _finish(self, retrieval: Retrieval, report: ScanReport, started: datetime) -> None:
        report.duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        retrieval.duration_ms = report.duration_ms
        retrieval.metadata_ = {
            "items_seen": report.items_seen,
            "items_new": report.items_new,
            "duplicates": report.duplicates,
        }
        self.session.flush()
