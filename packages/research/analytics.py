"""Analytics + comments (Doc 17 step 27; Doc 15).

Event model (Doc 15): never overwrite history — each collection appends a
new metric_event. Overview reads the LATEST collection per publication per
metric. Comments go through a deterministic classifier (collect → spam →
intent → qualified signal); testimony is classified POSSIBLE_ORAL_HISTORY
and is never treated as confirmation (Doc 15).
"""

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.enums import MetricName, QualifiedSignal
from packages.domain.models import Profile
from packages.domain.publishing import Comment, MetricEvent, Publication
from packages.governance.audit import append_audit
from packages.shared.execution_context import ExecutionContext

_SPAM_PATTERNS = (
    re.compile(r"http[s]?://\S+\s+\S*(ganhe|promo|grátis|gratis|clique)", re.I),
    re.compile(r"(ganhe seguidores|promoção imperdível|clique aqui para ganhar)", re.I),
)

def _sig(signal: QualifiedSignal, pattern: str):
    return (signal, re.compile(pattern, re.I))


_SOURCE = r"\b(qual|quais)?\s*(a|as)?\s*fonte(s)?|onde viu|onde você viu|mostra a fonte"
_CORRECTION = r"\b(errou|erro|correção|correcao|na verdade|não é isso|nao e isso|o certo é)\b"
_DOCUMENT = (
    r"\b(tenho (uma )?(foto|fotos|documento|carta)"
    r"|achei um documento|existe um documento)\b"
)
_TESTIMONY = (
    r"\b(meu avô|minha avó|meu avo|minha avo|trabalhou lá"
    r"|eu estava lá|eu estive|minha mãe contava|meu pai contava)\b"
)
_CONTINUATION = r"\b(e depois|continua|parte 2|faz mais|quero saber mais)\b"

_SIGNAL_PATTERNS = [
    _sig(QualifiedSignal.SOURCE_REQUEST, _SOURCE),
    _sig(QualifiedSignal.CORRECTION, _CORRECTION),
    _sig(QualifiedSignal.DOCUMENT_SUBMISSION, _DOCUMENT),
    _sig(QualifiedSignal.TESTIMONY, _TESTIMONY),
    _sig(QualifiedSignal.CONTINUATION_REQUEST, _CONTINUATION),
]


def classify_comment(text: str) -> tuple[str, str | None]:
    """Returns (intent, qualified_signal). Deterministic, pt-BR heuristics."""
    if not text or not text.strip():
        return ("EMPTY", None)
    for pattern in _SPAM_PATTERNS:
        if pattern.search(text):
            return ("SPAM", None)
    if text.strip().endswith("?"):
        # questions can be recurring questions or source requests — source wins
        for signal, pattern in _SIGNAL_PATTERNS:
            if signal is QualifiedSignal.SOURCE_REQUEST and pattern.search(text):
                return ("QUESTION", signal.value)
        return ("QUESTION", QualifiedSignal.RECURRING_QUESTION.value)
    for signal, pattern in _SIGNAL_PATTERNS:
        if pattern.search(text):
            return ("FEEDBACK", signal.value)
    return ("COMMENT", None)


class AnalyticsService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _publication_for_context(
        self, ctx: ExecutionContext, publication: Publication
    ) -> Publication:
        scoped = self.session.scalars(
            select(Publication).where(
                Publication.id == publication.id,
                Publication.workspace_id == ctx.workspace_id,
                Publication.profile_id == ctx.profile_id,
            )
        ).first()
        if scoped is None:
            raise LookupError("publication not found in profile")
        return scoped

    def _profile_exists(self, workspace_id, profile_id) -> bool:
        return (
            self.session.scalars(
                select(Profile.id).where(
                    Profile.id == profile_id,
                    Profile.workspace_id == workspace_id,
                )
            ).first()
            is not None
        )

    # --- metrics (append-only) ---------------------------------------------

    def record_metrics(
        self,
        ctx: ExecutionContext,
        publication: Publication,
        values: dict[str, int],
    ) -> int:
        """Each collection appends fresh metric_events — history is never
        overwritten (Doc 15)."""
        publication = self._publication_for_context(ctx, publication)
        count = 0
        for name, value in values.items():
            metric = MetricName(name.upper())
            self.session.add(
                MetricEvent(
                    workspace_id=ctx.workspace_id,
                    profile_id=publication.profile_id,
                    publication_id=publication.id,
                    metric=metric.value,
                    value=int(value),
                    collected_at=datetime.now(UTC),
                )
            )
            count += 1
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="METRICS_COLLECTED",
            entity_type="publication",
            entity_id=publication.id,
            new_state=f"{count} metrics",
        )
        return count

    def publication_snapshot(
        self, ctx: ExecutionContext, publication: Publication
    ) -> dict:
        """Latest value per metric for one publication."""
        pub = self._publication_for_context(ctx, publication)
        rows = self.session.execute(
            select(MetricEvent.metric, MetricEvent.value)
            .where(
                MetricEvent.publication_id == pub.id,
                MetricEvent.workspace_id == ctx.workspace_id,
                MetricEvent.profile_id == ctx.profile_id,
            )
            .order_by(MetricEvent.collected_at.desc())
        ).all()
        latest: dict[str, int] = {}
        for metric, value in rows:
            latest.setdefault(metric, value)  # first seen = most recent
        return {"publication_id": str(pub.id), "platform": pub.platform, "metrics": latest}

    def overview(self, workspace_id, profile_id) -> dict:
        """Profile overview: latest-per-metric summed over publications, plus
        publication counts by status."""
        publications = list(
            self.session.scalars(
                select(Publication).where(
                    Publication.workspace_id == workspace_id,
                    Publication.profile_id == profile_id,
                )
            )
        )
        totals: dict[str, int] = {}
        by_status: dict[str, int] = {}
        ctx = ExecutionContext(workspace_id=workspace_id, profile_id=profile_id)
        for pub in publications:
            by_status[pub.status] = by_status.get(pub.status, 0) + 1
            for metric, value in self.publication_snapshot(ctx, pub)["metrics"].items():
                totals[metric] = totals.get(metric, 0) + value
        return {
            "profile_id": str(profile_id),
            "publications": len(publications),
            "by_status": by_status,
            "totals": totals,
        }

    # --- comments ------------------------------------------------------------

    def add_comment(
        self,
        ctx: ExecutionContext,
        publication: Publication | None,
        *,
        text: str,
        author_ref: str | None = None,
    ) -> Comment:
        if ctx.profile_id is None or not self._profile_exists(ctx.workspace_id, ctx.profile_id):
            raise LookupError("profile not found in workspace")
        if publication is not None:
            publication = self._publication_for_context(ctx, publication)
        intent, signal = classify_comment(text)
        comment = Comment(
            workspace_id=ctx.workspace_id,
            profile_id=publication.profile_id if publication else ctx.profile_id,
            publication_id=publication.id if publication else None,
            author_ref=author_ref,
            text=text,
            intent=intent,
            qualified_signal=signal,
        )
        self.session.add(comment)
        self.session.flush()
        append_audit(
            self.session,
            ctx=ctx,
            action="COMMENT_COLLECTED",
            entity_type="comment",
            entity_id=comment.id,
            new_state=signal or intent,
        )
        return comment

    def qualified_signals(self, workspace_id, profile_id, limit: int = 100) -> list[Comment]:
        return list(
            self.session.scalars(
                select(Comment)
                .where(
                    Comment.workspace_id == workspace_id,
                    Comment.profile_id == profile_id,
                    Comment.qualified_signal.is_not(None),
                )
                .order_by(Comment.created_at.desc())
                .limit(limit)
            )
        )

    def list_comments(self, workspace_id, profile_id, limit: int = 100) -> list[Comment]:
        return list(
            self.session.scalars(
                select(Comment)
                .where(Comment.workspace_id == workspace_id, Comment.profile_id == profile_id)
                .order_by(Comment.created_at.desc())
                .limit(limit)
            )
        )
