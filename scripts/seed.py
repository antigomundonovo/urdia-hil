"""Seed the ANM profile (`python -m scripts.seed`, Doc 07).

Creates, idempotently: a dev workspace and the `antigo_mundo_novo` profile with
the exact configuration from the Constitution (Doc 00 §3). The full config is
stored verbatim in editorial_policy JSONB so nothing is lost or re-interpreted;
`language`/`audience_region`/`automation_level` columns mirror their spec keys.
"""

from sqlalchemy import select

from packages.domain.models import Profile, Workspace
from packages.shared.db import SessionLocal

ANM_PROFILE_KEY = "antigo_mundo_novo"

# Doc 00 §3 — PROFILE INICIAL — ANTIGO MUNDO NOVO (verbatim)
ANM_EDITORIAL_POLICY: dict = {
    "language": "pt-BR",
    "audience": "Brasil",
    "brazil_weight": 0.65,
    "world_weight": 0.35,
    "historical_depth": 7,
    "editorial_style": "acessível + curioso + documental",
    "image_first": True,
    "real_historical_assets_first": True,
    "ai_imagery": "secondary",
    "uncertainty": "required",
    "political_policy": "neutral_evidence_based",
    "human_approval_required": True,
    "automation_level": 2,
    "unknown_rights_block_publication": True,
}


def seed() -> None:
    with SessionLocal() as session:
        workspace = session.scalar(select(Workspace).where(Workspace.name == "URDIA"))
        if workspace is None:
            workspace = Workspace(name="URDIA")
            session.add(workspace)
            session.flush()

        profile = session.scalar(
            select(Profile).where(
                Profile.workspace_id == workspace.id, Profile.key == ANM_PROFILE_KEY
            )
        )
        if profile is None:
            profile = Profile(
                workspace_id=workspace.id,
                key=ANM_PROFILE_KEY,
                name="Antigo Mundo Novo",
            )
            session.add(profile)

        profile.language = ANM_EDITORIAL_POLICY["language"]
        profile.audience_region = ANM_EDITORIAL_POLICY["audience"]
        profile.automation_level = ANM_EDITORIAL_POLICY["automation_level"]
        profile.editorial_policy = ANM_EDITORIAL_POLICY
        profile.status = "ACTIVE"

        session.commit()
        print(f"seeded workspace={workspace.name} profile={profile.key}")


if __name__ == "__main__":
    seed()
