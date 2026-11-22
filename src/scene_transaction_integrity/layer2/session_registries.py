"""Managed Armature session identity and FAILED isolation registries migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2)."""

from typing import Any, Dict

from src.scene_transaction_integrity.layer2.session_records import (
    ArmatureSessionIdentityRecord,
)

_MANAGED_ARMATURE_IDENTITIES: Dict[str, ArmatureSessionIdentityRecord] = {}
_ISOLATED_FAILED_ARMATURES: Dict[str, Dict[str, Any]] = {}
