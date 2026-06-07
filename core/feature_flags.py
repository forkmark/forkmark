"""Three-level enterprise feature gating.

Feature availability is resolved in order:
  1. Environment variable  (global kill-switch / enable)
  2. Organization plan     (enterprise, team, free)
  3. Workspace setting     (per-workspace override stored in DB)

The first level that explicitly disables a feature wins.
If no level disables it, the feature is enabled.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Optional


class FeatureTier(str, Enum):
    FREE       = "free"
    TEAM       = "team"
    ENTERPRISE = "enterprise"


# ── Feature definitions ──────────────────────────────────────────────────────
# Maps feature_name -> minimum tier required.

_FEATURE_TIERS = {
    "agent_comparison": FeatureTier.FREE,   # available to all in v0.1.2
}

# Environment variable overrides: FM_ENABLE_<FEATURE_NAME> = true/false
_ENV_PREFIX = "FM_ENABLE_"


def _env_override(feature: str) -> Optional[bool]:
    """Check env var FM_ENABLE_<FEATURE>. Returns None if unset."""
    val = os.getenv(f"{_ENV_PREFIX}{feature.upper()}", "").strip().lower()
    if val in ("true", "1", "yes"):
        return True
    if val in ("false", "0", "no"):
        return False
    return None


def is_feature_enabled(
    feature: str,
    org_plan: str = "free",
    workspace_override: Optional[bool] = None,
) -> bool:
    """Resolve whether *feature* is active given current context.

    Parameters
    ----------
    feature : str
        Feature key, e.g. ``"agent_comparison"``.
    org_plan : str
        Current organization plan (``"free"`` / ``"team"`` / ``"enterprise"``).
    workspace_override : bool | None
        Per-workspace DB toggle.  ``None`` means "use default".

    Returns
    -------
    bool
    """
    # Level 1 — env var (global kill-switch)
    env = _env_override(feature)
    if env is not None:
        return env

    # Level 2 — org plan tier gate
    min_tier = _FEATURE_TIERS.get(feature)
    if min_tier is None:
        return False  # unknown feature -> disabled
    tier_order = [FeatureTier.FREE, FeatureTier.TEAM, FeatureTier.ENTERPRISE]
    try:
        plan_tier = FeatureTier(org_plan.lower())
    except ValueError:
        plan_tier = FeatureTier.FREE
    if tier_order.index(plan_tier) < tier_order.index(min_tier):
        return False

    # Level 3 — workspace override
    if workspace_override is not None:
        return workspace_override

    return True


def agent_comparison_enabled(
    org_plan: str = "free",
    workspace_override: Optional[bool] = None,
) -> bool:
    """Convenience wrapper for the agent_comparison feature."""
    return is_feature_enabled("agent_comparison", org_plan, workspace_override)
