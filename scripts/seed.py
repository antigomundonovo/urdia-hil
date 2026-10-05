"""Seed the default editorial profile (`python -m scripts.seed`, Doc 07).

Creates, idempotently, a dev workspace and a generic `default` profile. A
channel-specific identity can be configured later through the profile layer.
The full config is stored verbatim in editorial_policy JSONB so nothing is
lost or re-interpreted; `language`/`audience_region`/`automation_level`
columns mirror their spec keys.
"""

from sqlalchemy import select, text

from packages.domain.models import Profile, Workspace
from packages.domain.profile_defaults import DEFAULT_EDITORIAL_POLICY, DEFAULT_PROFILE_KEY
from packages.shared.db import SessionLocal


def ensure_database_is_ready() -> None:
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
    except Exception as exc:
        raise RuntimeError(
            "PostgreSQL not reachable. Start the database with: docker compose up -d postgres"
        ) from exc


def seed() -> None:
    ensure_database_is_ready()
    with SessionLocal() as session:
        workspace = session.scalar(select(Workspace).where(Workspace.name == "URDIA"))
        if workspace is None:
            workspace = Workspace(name="URDIA")
            session.add(workspace)
            session.flush()

        profile = session.scalar(
            select(Profile).where(
                Profile.workspace_id == workspace.id, Profile.key == DEFAULT_PROFILE_KEY
            )
        )
        if profile is None:
            profile = Profile(
                workspace_id=workspace.id,
                key=DEFAULT_PROFILE_KEY,
                name="Default Profile",
            )
            session.add(profile)

        profile.language = DEFAULT_EDITORIAL_POLICY["language"]
        profile.audience_region = DEFAULT_EDITORIAL_POLICY["audience"]
        profile.automation_level = DEFAULT_EDITORIAL_POLICY["automation_level"]
        profile.editorial_policy = DEFAULT_EDITORIAL_POLICY
        profile.status = "ACTIVE"

        session.commit()
        print(f"seeded workspace={workspace.name} profile={profile.key}")


if __name__ == "__main__":
    seed()
