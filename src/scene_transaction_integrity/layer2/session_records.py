"""Armature session identity enums and record migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2)."""

from enum import Enum
from typing import Any, Dict, Optional, Tuple

import bpy


class _ArmatureLivenessStatus(str, Enum):
    """Explicit liveness status for managed Armature session identities (Task 10-B-13)."""
    ALIVE_VERIFIED = "ALIVE_VERIFIED"
    INVALIDATED_DEAD = "INVALIDATED_DEAD"


class _ArmatureIsolationState(str, Enum):
    """Explicit FAILED isolation state for managed Armature session identities (Task 10-B-13)."""
    NONE = "NONE"
    ISOLATED_FAILED_B = "ISOLATED_FAILED_B"
    ISOLATED_FAILED_C = "ISOLATED_FAILED_C"
    TOMBSTONED_FAILED_D = "TOMBSTONED_FAILED_D"
    ARCHIVED_RETIRED = "ARCHIVED_RETIRED"


class ArmatureSessionIdentityRecord:
    """Layer 2 session identity record for a managed Armature (Task 10-B-13)."""

    def __init__(
        self,
        registry_session_id: str,
        original_blender_ref: Optional[bpy.types.Object],
        registration_pointer: int,
        original_data_pointer: int,
        liveness_status: _ArmatureLivenessStatus = _ArmatureLivenessStatus.ALIVE_VERIFIED,
        in_live_blender_collection: bool = True,
        isolation_state: _ArmatureIsolationState = _ArmatureIsolationState.NONE,
        tombstone_record: Optional[Dict[str, Any]] = None,
        original_data_ref: Optional[Any] = None,
        registered_name_snapshot: str = "",
        lifecycle_stage: str = "REGISTERED_ALIVE",
    ) -> None:
        self.registry_session_id: str = str(registry_session_id)
        self.original_blender_ref: Optional[bpy.types.Object] = original_blender_ref
        self.registration_pointer: int = int(registration_pointer)
        self.original_data_pointer: int = int(original_data_pointer)
        self.liveness_status: _ArmatureLivenessStatus = (
            liveness_status
            if isinstance(liveness_status, _ArmatureLivenessStatus)
            else _ArmatureLivenessStatus(liveness_status)
        )
        self.in_live_blender_collection: bool = bool(in_live_blender_collection)
        self.isolation_state: _ArmatureIsolationState = (
            isolation_state
            if isinstance(isolation_state, _ArmatureIsolationState)
            else _ArmatureIsolationState(isolation_state)
        )
        self.tombstone_record: Optional[Dict[str, Any]] = tombstone_record
        self.original_data_ref: Optional[Any] = original_data_ref
        self.registered_name_snapshot: str = str(registered_name_snapshot)
        self.lifecycle_stage: str = str(lifecycle_stage)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "registry_session_id": self.registry_session_id,
            "original_blender_ref": self.original_blender_ref,
            "registration_pointer": self.registration_pointer,
            "original_data_pointer": self.original_data_pointer,
            "liveness_status": (
                self.liveness_status.value
                if isinstance(self.liveness_status, Enum)
                else str(self.liveness_status)
            ),
            "in_live_blender_collection": self.in_live_blender_collection,
            "isolation_state": (
                self.isolation_state.value
                if isinstance(self.isolation_state, Enum)
                else str(self.isolation_state)
            ),
            "tombstone_record": self.tombstone_record,
            "original_data_ref": self.original_data_ref,
            "registered_name_snapshot": self.registered_name_snapshot,
            "lifecycle_stage": self.lifecycle_stage,
        }

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self) -> Tuple[str, ...]:
        return (
            "registry_session_id",
            "original_blender_ref",
            "registration_pointer",
            "original_data_pointer",
            "liveness_status",
            "in_live_blender_collection",
            "isolation_state",
            "tombstone_record",
            "original_data_ref",
            "registered_name_snapshot",
            "lifecycle_stage",
        )
