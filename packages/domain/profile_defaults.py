"""Source-of-truth defaults for new and legacy editorial profiles.

The default profile is deliberately domain-neutral. ANM remains available as a
legacy compatibility profile for existing History Intelligence Layer workspaces.
"""

DEFAULT_PROFILE_KEY = "default"
DEFAULT_EDITORIAL_POLICY: dict = {
    "language": "pt-BR",
    "audience": "Brasil",
    "editorial_style": "acessível + claro + documental",
    "image_first": True,
    "uncertainty": "required",
    "political_policy": "neutral_evidence_based",
    "human_approval_required": True,
    "automation_level": 2,
    "unknown_rights_block_publication": True,
}

ANM_PROFILE_KEY = "antigo_mundo_novo"
ANM_EDITORIAL_POLICY: dict = {
    **DEFAULT_EDITORIAL_POLICY,
    "brazil_weight": 0.65,
    "world_weight": 0.35,
    "historical_depth": 7,
    "editorial_style": "acessível + curioso + documental",
    "real_historical_assets_first": True,
    "ai_imagery": "secondary",
    "legacy_channel_identity": "Antigo Mundo Novo",
}
