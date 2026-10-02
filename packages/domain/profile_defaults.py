"""Source-of-truth defaults for a new editorial profile.

ANM_* remains as a legacy compatibility profile for existing workspaces.
New workspaces must not inherit a channel-specific identity.
"""

DEFAULT_PROFILE_KEY = "default"
DEFAULT_EDITORIAL_POLICY: dict = {
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

ANM_PROFILE_KEY = "antigo_mundo_novo"
ANM_EDITORIAL_POLICY = DEFAULT_EDITORIAL_POLICY.copy()
ANM_EDITORIAL_POLICY["legacy_channel_identity"] = "Antigo Mundo Novo"
