"""Managed Armature session identity registry migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 Registry Batch 3)."""

from typing import Dict

from src.scene_transaction_integrity.layer2.session_records import (
    ArmatureSessionIdentityRecord,
)

_MANAGED_ARMATURE_IDENTITIES: Dict[str, ArmatureSessionIdentityRecord] = {}
