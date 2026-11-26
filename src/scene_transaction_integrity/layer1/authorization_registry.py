"""Coordinator authorization grant registry and TTL migrated from `src/rig/arm_ik.py` (Task 10-B Layer 1 L1-12)."""

from typing import Any, Dict

_COORDINATOR_AUTHORIZATION_GRANTS: Dict[str, Dict[str, Any]] = {}

# Coordinator grants are process-local, ephemeral capabilities, not long-lived
# isolation records. Expiration is evaluated lazily at issuance/consumption;
# expired or superseded capabilities can never be used to clear isolation.
_COORDINATOR_GRANT_TTL_SECONDS: float = 60.0
