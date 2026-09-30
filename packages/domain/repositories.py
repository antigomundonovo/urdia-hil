"""Repository layer (Doc 17 step 6).

Every read is scoped: fetch-by-id methods require the caller's workspace_id
and return None on mismatch (Doc 08 — server-side membership check, fail
closed). AuditRepository exposes append + read only: audit is append-only
(Doc 08); no update/delete paths exist in the application layer.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.models import AuditEvent, Job, Profile, Workspace, WorkspaceMember


class WorkspaceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, workspace_id: UUID) -> Workspace | None:
        return self.session.get(Workspace, workspace_id)

    def ensure(self, name: str) -> Workspace:
        ws = self.session.scalar(select(Workspace).where(Workspace.name == name))
        if ws is None:
            ws = Workspace(name=name)
            self.session.add(ws)
            self.session.flush()
        return ws

    def add_member(self, workspace_id: UUID, user_id: UUID) -> None:
        self.session.add(WorkspaceMember(workspace_id=workspace_id, user_id=user_id))
        self.session.flush()


class ProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_scoped(self, profile_id: UUID, workspace_id: UUID) -> Profile | None:
        """Fail closed: None unless the profile belongs to the caller's workspace."""
        profile = self.session.get(Profile, profile_id)
        if profile is None or profile.workspace_id != workspace_id:
            return None
        return profile

    def get_by_key(self, workspace_id: UUID, key: str) -> Profile | None:
        return self.session.scalar(
            select(Profile).where(Profile.workspace_id == workspace_id, Profile.key == key)
        )

    def list_for_workspace(self, workspace_id: UUID) -> list[Profile]:
        return list(
            self.session.scalars(
                select(Profile).where(Profile.workspace_id == workspace_id).order_by(Profile.key)
            )
        )


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        workspace_id: UUID,
        profile_id: UUID | None,
        job_type: str,
        payload: dict[str, Any] | None = None,
        max_attempts: int | None = None,
    ) -> Job:
        job = Job(
            workspace_id=workspace_id,
            profile_id=profile_id,
            job_type=job_type,
            payload=payload or {},
            max_attempts=max_attempts,
        )
        self.session.add(job)
        self.session.flush()
        return job

    def get_scoped(self, job_id: UUID, workspace_id: UUID) -> Job | None:
        job = self.session.get(Job, job_id)
        if job is None or job.workspace_id != workspace_id:
            return None
        return job

    def list_for_profile(self, workspace_id: UUID, profile_id: UUID) -> list[Job]:
        return list(
            self.session.scalars(
                select(Job)
                .where(Job.workspace_id == workspace_id, Job.profile_id == profile_id)
                .order_by(Job.created_at.desc())
            )
        )

    def pending_for_workspace(self, workspace_id: UUID) -> list[Job]:
        return list(
            self.session.scalars(
                select(Job).where(
                    Job.workspace_id == workspace_id, Job.status == "PENDING"
                )
            )
        )


class AuditRepository:
    """Append-only (Doc 08): corrections create new events; nothing updates
    or deletes audit rows through the application layer."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def append(
        self,
        *,
        workspace_id: UUID,
        profile_id: UUID | None,
        actor_id: UUID | None,
        action: str,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        previous_state: str | None = None,
        new_state: str | None = None,
        reason: str | None = None,
        rule_version: str | None = None,
        provider: str | None = None,
        evidence_ids: list[Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            workspace_id=workspace_id,
            profile_id=profile_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_state=previous_state,
            new_state=new_state,
            reason=reason,
            rule_version=rule_version,
            provider=provider,
            evidence_ids=evidence_ids,
            metadata_=metadata,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def list_for_workspace(
        self,
        workspace_id: UUID,
        profile_id: UUID | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        stmt = select(AuditEvent).where(AuditEvent.workspace_id == workspace_id)
        if profile_id is not None:
            stmt = stmt.where(AuditEvent.profile_id == profile_id)
        stmt = stmt.order_by(AuditEvent.timestamp.desc()).limit(limit)
        return list(self.session.scalars(stmt))

    def count_calls_since(self, capability_key: str, since: datetime, workspace_id: UUID) -> int:
        """Usage counting for quota enforcement counts audit events — audit is
        the single source of call history (Doc 05: pipeline always ends in audit)."""
        stmt = (
            select(AuditEvent.id)
            .where(
                AuditEvent.workspace_id == workspace_id,
                AuditEvent.action == "CAPABILITY_CALL",
                AuditEvent.timestamp >= since,
            )
            .where(AuditEvent.metadata_["capability"].as_string() == capability_key)
        )
        return len(list(self.session.scalars(stmt)))
