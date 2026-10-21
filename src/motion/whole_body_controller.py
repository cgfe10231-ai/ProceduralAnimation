"""Unified Whole-Body Control Interface and Minimal Coordinator (Task 6F-D).

Physics-constraint-assisted procedural animation: establishes a unified, extensible
whole-body controller coordinating:
- Independent bilateral Hand IK (world position & 3D orientation targets, reach clamping).
- Independent bilateral Foot IK (world position, foot roll/pitch rotation, stance locks).
- Base floating frame targets (CharacterRoot world position & yaw, pelvis offset & tilt).
- Trunk FK targets (spine, neck, head).
- End-effector weights and enabled/disabled states.
- Non-destructive ROM validation via JointModel and evaluated IK rotation checks.
- Real-time Center of Mass (CoM) evaluation via rigid_link.
- Explicit detection and truthful reporting of reachability, ROM violations, and ROM-vs-target conflicts.
- 100% backward-compatible with existing MotionPlanner, MotionAction, and rig hierarchies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import bpy
from mathutils import Euler, Matrix, Vector

from src.config import PipelineConfig
from src.motion.joint_limits import (
    DEFAULT_HUMANOID_ROM_MODEL,
    JointClampResult,
    JointModel,
    JointValidationResult,
    extract_evaluated_bone_rotation_rad,
)
from src.motion.rigid_link import (
    DEMPSTER_WINTER_15_SEGMENT_MODEL,
    BodyMassDistribution,
    WholeBodyCoMResult,
    compute_whole_body_com,
)
from src.rig.arm_ik import (
    MAX_ARM_REACH,
    MIN_ARM_REACH,
    get_arm_ik_state,
    reset_arm_ik,
    set_arm_ik_influence,
    set_hand_ik_target,
    setup_arm_ik,
)
from src.rig.foot_contact import (
    evaluate_foot_support,
    lock_foot_contact,
    unlock_foot_contact,
)
from src.rig.ik import (
    IK_TARGET_NAMES,
    MAX_LEG_REACH,
    MIN_LEG_REACH,
    get_leg_ik_state,
    reset_leg_ik,
    set_foot_ik_target,
    setup_leg_ik,
)
from src.rig.pose import reset_pose


# =============================================================================
# Target Specifications
# =============================================================================

@dataclass
class EndEffectorTarget:
    """Independent spatial target specification for a single limb end effector (Hand or Foot)."""
    effector_id: str                                                  # "hand_L", "hand_R", "foot_L", "foot_R"
    target_world_xyz: Tuple[float, float, float]                      # World-space position in meters
    target_rotation_deg: Optional[Tuple[float, float, float]] = None  # World-space Euler rotation in degrees (roll, pitch, yaw)
    pole_hint_world_xyz: Optional[Tuple[float, float, float]] = None  # Optional pole vector guidance position
    enabled: bool = True                                              # True to activate IK; False to leave in FK mode
    weight: float = 1.0                                               # Blend weight / influence in [0.0, 1.0]
    is_locked: bool = False                                           # Foot ground support lock flag
    clamp_reach: bool = True                                          # Project to maximum reach sphere if out of reach


@dataclass
class WholeBodyControlTargets:
    """Unified container for all whole-body kinematic and posture targets at a discrete frame."""
    # End effectors
    hand_L: Optional[EndEffectorTarget] = None
    hand_R: Optional[EndEffectorTarget] = None
    foot_L: Optional[EndEffectorTarget] = None
    foot_R: Optional[EndEffectorTarget] = None

    # Base / Floating frame targets
    root_position: Optional[Tuple[float, float, float]] = None        # CharacterRoot world coordinates (x, y, z)
    root_yaw_deg: Optional[float] = None                              # CharacterRoot world heading yaw angle (deg)
    pelvis_location: Optional[Tuple[float, float, float]] = None      # Pelvis bone local translation offset (m)
    pelvis_rotation_deg: Optional[Tuple[float, float, float]] = None  # Pelvis bone local Euler rotation (deg)

    # Axial / Trunk FK posture targets
    spine_rotation_deg: Optional[Tuple[float, float, float]] = None   # spine bone local Euler rotation (deg)
    neck_rotation_deg: Optional[Tuple[float, float, float]] = None    # neck bone local Euler rotation (deg)
    head_rotation_deg: Optional[Tuple[float, float, float]] = None    # head bone local Euler rotation (deg)

    # Generic FK overrides for any bone
    fk_joint_rotations_deg: Dict[str, Tuple[float, float, float]] = field(default_factory=dict)

    # Fluent Builder Helpers
    def set_hand(
        self,
        side: str,
        target_world_xyz: Tuple[float, float, float],
        rotation_deg: Optional[Tuple[float, float, float]] = None,
        pole_hint_xyz: Optional[Tuple[float, float, float]] = None,
        weight: float = 1.0,
        enabled: bool = True,
        clamp_reach: bool = True,
    ) -> WholeBodyControlTargets:
        side_upper = side.upper()
        eff_id = f"hand_{side_upper}"
        target = EndEffectorTarget(
            effector_id=eff_id,
            target_world_xyz=target_world_xyz,
            target_rotation_deg=rotation_deg,
            pole_hint_world_xyz=pole_hint_xyz,
            enabled=enabled,
            weight=weight,
            clamp_reach=clamp_reach,
        )
        if side_upper == "L":
            self.hand_L = target
        elif side_upper == "R":
            self.hand_R = target
        else:
            raise ValueError(f"Invalid hand side: {side}")
        return self

    def set_foot(
        self,
        side: str,
        target_world_xyz: Tuple[float, float, float],
        rotation_deg: Optional[Tuple[float, float, float]] = None,
        pole_hint_xyz: Optional[Tuple[float, float, float]] = None,
        weight: float = 1.0,
        is_locked: bool = False,
        enabled: bool = True,
        clamp_reach: bool = True,
    ) -> WholeBodyControlTargets:
        side_upper = side.upper()
        eff_id = f"foot_{side_upper}"
        target = EndEffectorTarget(
            effector_id=eff_id,
            target_world_xyz=target_world_xyz,
            target_rotation_deg=rotation_deg,
            pole_hint_world_xyz=pole_hint_xyz,
            enabled=enabled,
            weight=weight,
            is_locked=is_locked,
            clamp_reach=clamp_reach,
        )
        if side_upper == "L":
            self.foot_L = target
        elif side_upper == "R":
            self.foot_R = target
        else:
            raise ValueError(f"Invalid foot side: {side}")
        return self

    def set_root(
        self,
        position: Optional[Tuple[float, float, float]] = None,
        yaw_deg: Optional[float] = None,
    ) -> WholeBodyControlTargets:
        self.root_position = position
        self.root_yaw_deg = yaw_deg
        return self

    def set_pelvis(
        self,
        location: Optional[Tuple[float, float, float]] = None,
        rotation_deg: Optional[Tuple[float, float, float]] = None,
    ) -> WholeBodyControlTargets:
        self.pelvis_location = location
        self.pelvis_rotation_deg = rotation_deg
        return self

    def set_trunk_posture(
        self,
        spine_deg: Optional[Tuple[float, float, float]] = None,
        neck_deg: Optional[Tuple[float, float, float]] = None,
        head_deg: Optional[Tuple[float, float, float]] = None,
    ) -> WholeBodyControlTargets:
        self.spine_rotation_deg = spine_deg
        self.neck_rotation_deg = neck_deg
        self.head_rotation_deg = head_deg
        return self


# =============================================================================
# Feedback and Reporting Structures
# =============================================================================

@dataclass(frozen=True)
class UnmetConstraint:
    """Detailed record of an unsatisfied physical or kinematic constraint."""
    category: str        # "REACHABILITY", "ROM_VIOLATION", "ROM_CONFLICT", "DISALLOWED_DOF"
    target_name: str     # e.g., "hand_L", "shin.R", "spine"
    description: str     # Human-readable explanation of why the constraint failed
    error_amount: float  # Quantitative metric of violation (meters or degrees)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EndEffectorFeedback:
    """Evaluated execution metrics for a single end effector."""
    effector_id: str
    enabled: bool
    weight: float
    requested_world_xyz: Tuple[float, float, float]
    actual_world_xyz: Tuple[float, float, float]
    position_error_m: float
    requested_rotation_deg: Optional[Tuple[float, float, float]] = None
    actual_rotation_deg: Optional[Tuple[float, float, float]] = None
    orientation_error_deg: Optional[float] = None
    is_reachable: bool = True
    strictly_in_reach: bool = True
    reach_distance_m: float = 0.0
    max_reach_m: float = 0.0


@dataclass
class WholeBodyControlResult:
    """Comprehensive output produced by WholeBodyController for a single execution frame."""
    success: bool                                         # True ONLY if all enabled targets are met without ROM violations
    end_effectors: Dict[str, EndEffectorFeedback]         # Per-effector tracking feedback
    rom_validation: JointValidationResult                 # Evaluated ROM check result across all joints
    com_result: WholeBodyCoMResult                        # Evaluated whole-body CoM
    unmet_constraints: List[UnmetConstraint]              # Explicit list of unmet constraints with failure reasons
    root_world_position: Tuple[float, float, float]       # Actual evaluated root position
    pelvis_world_position: Tuple[float, float, float]     # Actual evaluated pelvis position
    max_end_effector_error_m: float                       # Maximum position error among active effectors
    has_rom_violation: bool                               # True if any joint exceeds anatomical ROM
    is_all_reachable: bool                                # True if all requested targets are within kinematic reach

    def summary(self) -> str:
        status_str = "SUCCESS" if self.success else "FAILED / UNMET CONSTRAINTS"
        lines = [
            f"[WholeBodyControlResult: {status_str}]",
            f"  Root: ({self.root_world_position[0]:.3f}, {self.root_world_position[1]:.3f}, {self.root_world_position[2]:.3f}) | Pelvis: ({self.pelvis_world_position[0]:.3f}, {self.pelvis_world_position[1]:.3f}, {self.pelvis_world_position[2]:.3f})",
            f"  CoM World: ({self.com_result.com_world.x:.4f}, {self.com_result.com_world.y:.4f}, {self.com_result.com_world.z:.4f}) m",
            f"  Max End-Effector Error: {self.max_end_effector_error_m * 1000:.3f} mm | ROM Valid: {not self.has_rom_violation} | All Reachable: {self.is_all_reachable}",
        ]
        for eff_id, fb in self.end_effectors.items():
            if fb.enabled:
                rot_info = f", rot_err={fb.orientation_error_deg:.2f} deg" if fb.orientation_error_deg is not None else ""
                lines.append(
                    f"  - {eff_id:8s}: err={fb.position_error_m * 1000:.3f} mm (dist={fb.reach_distance_m:.3f}/{fb.max_reach_m:.3f}m, reachable={fb.is_reachable}{rot_info})"
                )
        if self.unmet_constraints:
            lines.append(f"  Unmet Constraints ({len(self.unmet_constraints)}):")
            for uc in self.unmet_constraints:
                lines.append(f"    * [{uc.category}] {uc.target_name}: {uc.description} (metric={uc.error_amount:.4f})")
        return "\n".join(lines)


# =============================================================================
# WholeBodyController Class
# =============================================================================

class WholeBodyController:
    """Minimal unified whole-body coordinator integrating FK, IK, ROM, and CoM.

    Reuses existing Blender constraints, Arm IK, Leg IK, rigid_link CoM, and JointModel ROM.
    Does NOT construct a secondary IK solver or alter rig hierarchies.
    """

    def __init__(
        self,
        armature_obj: Optional[bpy.types.Object] = None,
        root_obj: Optional[bpy.types.Object] = None,
        joint_model: Optional[JointModel] = None,
        mass_distribution: Optional[BodyMassDistribution] = None,
        config: Optional[PipelineConfig] = None,
    ) -> None:
        self.config = config or PipelineConfig()
        if armature_obj is None:
            armature_obj = bpy.data.objects.get("CharacterArmature")
        if armature_obj is None or armature_obj.type != "ARMATURE":
            raise RuntimeError("Valid CharacterArmature object not found in scene")
        self.armature_obj = armature_obj

        if root_obj is None:
            root_obj = self.armature_obj.parent or bpy.data.objects.get("CharacterRoot")
        self.root_obj = root_obj

        self.joint_model = joint_model or DEFAULT_HUMANOID_ROM_MODEL
        self.mass_distribution = mass_distribution or DEMPSTER_WINTER_15_SEGMENT_MODEL

        # Ensure IK constraints exist on the rig
        setup_leg_ik(self.armature_obj)
        setup_arm_ik(self.armature_obj, initial_influence=0.0)

    def execute_frame(
        self,
        targets: WholeBodyControlTargets,
        update_scene: bool = True,
        enforce_rom_clamping: bool = False,
        tolerance_position_m: float = 0.005,
        tolerance_rotation_deg: float = 1.0,
    ) -> WholeBodyControlResult:
        """Execute a single-frame whole-body posture and tracking dispatch.

        Workflow:
            ControlTargets -> Existing IK/FK -> Scene Update -> End-Effector Tracking
            -> ROM Validation -> CoM Evaluation -> Truthful Conflict Analysis -> Result

        Args:
            targets: Coordinated whole-body targets.
            update_scene: If True, calls view_layer.update() after applying transforms.
            enforce_rom_clamping: If True, clamps out-of-range joints to ROM and truthfully
                                  re-evaluates end-effector tracking (reporting any conflicts).
            tolerance_position_m: Acceptable reach error in meters (default 5mm).
            tolerance_rotation_deg: Acceptable orientation error in degrees (default 1.0 deg).

        Returns:
            WholeBodyControlResult with complete metrics, feedback, and constraint status.
        """
        arm = self.armature_obj
        root = self.root_obj

        # ---------------------------------------------------------------------
        # 1. Base / Floating Frame Dispatch
        # ---------------------------------------------------------------------
        if targets.root_position is not None and root is not None:
            root.location = Vector(targets.root_position)

        if targets.root_yaw_deg is not None and root is not None:
            root.rotation_mode = "XYZ"
            root.rotation_euler.z = math.radians(targets.root_yaw_deg)

        p_pelvis = arm.pose.bones.get("pelvis")
        if p_pelvis is not None:
            if targets.pelvis_location is not None:
                p_pelvis.location = Vector(targets.pelvis_location)
            if targets.pelvis_rotation_deg is not None:
                p_pelvis.rotation_mode = "XYZ"
                rx, ry, rz = (math.radians(v) for v in targets.pelvis_rotation_deg)
                p_pelvis.rotation_euler = Euler((rx, ry, rz), "XYZ")

        # ---------------------------------------------------------------------
        # 2. Axial / Trunk Posture FK Dispatch
        # ---------------------------------------------------------------------
        if targets.spine_rotation_deg is not None:
            pb = arm.pose.bones.get("spine")
            if pb is not None:
                pb.rotation_mode = "XYZ"
                pb.rotation_euler = Euler(tuple(math.radians(v) for v in targets.spine_rotation_deg), "XYZ")

        if targets.neck_rotation_deg is not None:
            pb = arm.pose.bones.get("neck")
            if pb is not None:
                pb.rotation_mode = "XYZ"
                pb.rotation_euler = Euler(tuple(math.radians(v) for v in targets.neck_rotation_deg), "XYZ")

        if targets.head_rotation_deg is not None:
            pb = arm.pose.bones.get("head")
            if pb is not None:
                pb.rotation_mode = "XYZ"
                pb.rotation_euler = Euler(tuple(math.radians(v) for v in targets.head_rotation_deg), "XYZ")

        for b_name, rot_deg in targets.fk_joint_rotations_deg.items():
            pb = arm.pose.bones.get(b_name)
            if pb is not None:
                pb.rotation_mode = "XYZ"
                pb.rotation_euler = Euler(tuple(math.radians(v) for v in rot_deg), "XYZ")

        # ---------------------------------------------------------------------
        # 3. Leg IK Dispatch (Left and Right)
        # ---------------------------------------------------------------------
        leg_targets = [("L", targets.foot_L), ("R", targets.foot_R)]
        for side, foot_tgt in leg_targets:
            if foot_tgt is not None and foot_tgt.enabled and foot_tgt.weight > 0.0:
                ik_name = IK_TARGET_NAMES.get(side)
                ik_obj = bpy.data.objects.get(ik_name) if ik_name else None
                was_locked = bool(ik_obj.get("is_locked", False)) if ik_obj is not None else False

                if foot_tgt.is_locked:
                    cur_locked_pt = tuple(ik_obj.get("contact_world_xyz", ())) if ik_obj is not None else ()
                    loc_diff = math.dist(cur_locked_pt, foot_tgt.target_world_xyz) if len(cur_locked_pt) == 3 else 999.0
                    if not was_locked or loc_diff > 0.001:
                        lock_foot_contact(
                            arm,
                            side,
                            contact_world_xyz=foot_tgt.target_world_xyz,
                            target_rotation_deg=foot_tgt.target_rotation_deg,
                        )
                    else:
                        evaluate_foot_support(arm, side)
                else:
                    if was_locked:
                        unlock_foot_contact(arm, side, reparent_to_root=True)
                    set_foot_ik_target(
                        arm,
                        side,
                        world_xyz=foot_tgt.target_world_xyz,
                        foot_rotation_deg=foot_tgt.target_rotation_deg,
                        clamp_reach=foot_tgt.clamp_reach,
                        clamp_ground=True,
                    )

        # ---------------------------------------------------------------------
        # 4. Hand IK Dispatch (Left and Right)
        # ---------------------------------------------------------------------
        arm_targets = [("L", targets.hand_L), ("R", targets.hand_R)]
        for side, hand_tgt in arm_targets:
            if hand_tgt is not None and hand_tgt.enabled and hand_tgt.weight > 0.0:
                set_hand_ik_target(
                    arm,
                    side,
                    world_xyz=hand_tgt.target_world_xyz,
                    hand_rotation_deg=hand_tgt.target_rotation_deg,
                    pole_world_xyz=hand_tgt.pole_hint_world_xyz,
                    clamp_reach=hand_tgt.clamp_reach,
                    influence=hand_tgt.weight,
                )
            else:
                set_arm_ik_influence(arm, side, influence=0.0)

        # Update scene to evaluate native Blender IK solvers
        if update_scene:
            bpy.context.view_layer.update()

        # ---------------------------------------------------------------------
        # 5. End-Effector Tracking & Error Evaluation
        # ---------------------------------------------------------------------
        effectors_feedback: Dict[str, EndEffectorFeedback] = {}
        unmet_constraints: List[UnmetConstraint] = []
        max_effector_error = 0.0
        all_reachable = True

        # Evaluate Foot IK tracking
        for side, foot_tgt in leg_targets:
            eff_id = f"foot_{side}"
            if foot_tgt is None or not foot_tgt.enabled:
                p_foot = arm.pose.bones.get(f"foot.{side}")
                actual_pos = (arm.matrix_world @ p_foot.head).to_tuple() if p_foot else (0.0, 0.0, 0.0)
                effectors_feedback[eff_id] = EndEffectorFeedback(
                    effector_id=eff_id,
                    enabled=False,
                    weight=0.0,
                    requested_world_xyz=(0.0, 0.0, 0.0),
                    actual_world_xyz=actual_pos,
                    position_error_m=0.0,
                    is_reachable=True,
                    strictly_in_reach=True,
                    reach_distance_m=0.0,
                    max_reach_m=MAX_LEG_REACH,
                )
                continue

            leg_state = get_leg_ik_state(arm, side)
            actual_pos = leg_state["ankle_world"].to_tuple()
            req_pos = foot_tgt.target_world_xyz
            pos_err = (Vector(actual_pos) - Vector(req_pos)).length
            hip_pos = leg_state["hip_world"]
            req_dist_from_hip = (Vector(req_pos) - hip_pos).length
            actual_dist_from_hip = (leg_state["ankle_world"] - hip_pos).length
            is_reach = (req_dist_from_hip <= MAX_LEG_REACH + 1e-4)

            max_effector_error = max(max_effector_error, pos_err)
            if not is_reach or pos_err > tolerance_position_m:
                all_reachable = False
                unmet_constraints.append(
                    UnmetConstraint(
                        category="REACHABILITY",
                        target_name=eff_id,
                        description=f"Foot {side} target exceeds maximum leg reach ({req_dist_from_hip:.3f}m > {MAX_LEG_REACH:.3f}m) or tracking error {pos_err*1000:.1f}mm > {tolerance_position_m*1000:.1f}mm",
                        error_amount=pos_err,
                        details={"requested_reach": req_dist_from_hip, "applied_reach": actual_dist_from_hip, "max_reach": MAX_LEG_REACH},
                    )
                )

            effectors_feedback[eff_id] = EndEffectorFeedback(
                effector_id=eff_id,
                enabled=True,
                weight=foot_tgt.weight,
                requested_world_xyz=req_pos,
                actual_world_xyz=actual_pos,
                position_error_m=pos_err,
                requested_rotation_deg=foot_tgt.target_rotation_deg,
                is_reachable=is_reach,
                strictly_in_reach=(req_dist_from_hip <= MAX_LEG_REACH + 1e-4),
                reach_distance_m=actual_dist_from_hip,
                max_reach_m=MAX_LEG_REACH,
            )

        # Evaluate Hand IK tracking
        for side, hand_tgt in arm_targets:
            eff_id = f"hand_{side}"
            if hand_tgt is None or not hand_tgt.enabled or hand_tgt.weight <= 0.0:
                p_hand = arm.pose.bones.get(f"hand.{side}")
                actual_pos = (arm.matrix_world @ p_hand.head).to_tuple() if p_hand else (0.0, 0.0, 0.0)
                effectors_feedback[eff_id] = EndEffectorFeedback(
                    effector_id=eff_id,
                    enabled=False,
                    weight=0.0,
                    requested_world_xyz=(0.0, 0.0, 0.0),
                    actual_world_xyz=actual_pos,
                    position_error_m=0.0,
                    is_reachable=True,
                    strictly_in_reach=True,
                    reach_distance_m=0.0,
                    max_reach_m=MAX_ARM_REACH,
                )
                continue

            arm_state = get_arm_ik_state(arm, side)
            actual_pos = arm_state["wrist_world"].to_tuple()
            req_pos = hand_tgt.target_world_xyz
            pos_err = (Vector(actual_pos) - Vector(req_pos)).length
            rot_err = float(arm_state["rotation_error_deg"]) if hand_tgt.target_rotation_deg is not None else None
            shoulder_pos = arm_state["shoulder_world"]
            req_dist_from_shoulder = (Vector(req_pos) - shoulder_pos).length
            actual_dist_from_shoulder = (arm_state["wrist_world"] - shoulder_pos).length
            is_reach = (MIN_ARM_REACH <= req_dist_from_shoulder <= MAX_ARM_REACH + 1e-4)

            max_effector_error = max(max_effector_error, pos_err)
            if not is_reach or pos_err > tolerance_position_m:
                all_reachable = False
                unmet_constraints.append(
                    UnmetConstraint(
                        category="REACHABILITY",
                        target_name=eff_id,
                        description=f"Hand {side} target exceeds maximum arm reach ({req_dist_from_shoulder:.3f}m > {MAX_ARM_REACH:.3f}m) or tracking error {pos_err*1000:.1f}mm > {tolerance_position_m*1000:.1f}mm",
                        error_amount=pos_err,
                        details={"requested_reach": req_dist_from_shoulder, "applied_reach": actual_dist_from_shoulder, "max_reach": MAX_ARM_REACH},
                    )
                )

            if rot_err is not None and rot_err > tolerance_rotation_deg:
                unmet_constraints.append(
                    UnmetConstraint(
                        category="ORIENTATION_ERROR",
                        target_name=eff_id,
                        description=f"Hand {side} 3D orientation alignment error {rot_err:.2f} deg > tolerance {tolerance_rotation_deg:.1f} deg",
                        error_amount=rot_err,
                    )
                )

            actual_rot_deg = tuple(arm_state["hand_world_euler_deg"]) if arm_state.get("hand_world_euler_deg") is not None else None
            effectors_feedback[eff_id] = EndEffectorFeedback(
                effector_id=eff_id,
                enabled=True,
                weight=hand_tgt.weight,
                requested_world_xyz=req_pos,
                actual_world_xyz=actual_pos,
                position_error_m=pos_err,
                requested_rotation_deg=hand_tgt.target_rotation_deg,
                actual_rotation_deg=actual_rot_deg,
                orientation_error_deg=rot_err,
                is_reachable=is_reach,
                strictly_in_reach=(req_dist_from_shoulder < MAX_ARM_REACH - 1e-4),
                reach_distance_m=actual_dist_from_shoulder,
                max_reach_m=MAX_ARM_REACH,
            )

        # ---------------------------------------------------------------------
        # 6. Anatomical Joint ROM Validation (Evaluated Active Pose)
        # ---------------------------------------------------------------------
        rom_validation = self.joint_model.validate_armature_pose(arm, use_evaluated_ik=True)
        if not rom_validation.is_valid:
            for b_name, viol in rom_validation.violations.items():
                unmet_constraints.append(
                    UnmetConstraint(
                        category="ROM_VIOLATION",
                        target_name=b_name,
                        description=f"Joint '{b_name}' ({viol.joint_id}) violates anatomical ROM by max {viol.max_excess_deg:.2f} deg",
                        error_amount=viol.max_excess_deg,
                        details={"joint_id": viol.joint_id, "violations": viol.axis_violations},
                    )
                )

        # ---------------------------------------------------------------------
        # 7. Truthful ROM Clamping & Conflict Enforcement (if requested)
        # ---------------------------------------------------------------------
        if enforce_rom_clamping and not rom_validation.is_valid:
            # Clamping FK pose bones
            self.joint_model.clamp_armature_pose(arm, apply=True, update_scene=True)

            # Truthfully re-evaluate end-effector actual errors
            for side, hand_tgt in arm_targets:
                eff_id = f"hand_{side}"
                if hand_tgt is not None and hand_tgt.enabled:
                    arm_st = get_arm_ik_state(arm, side)
                    new_pos_err = float(arm_st["target_error"])
                    if new_pos_err > tolerance_position_m:
                        unmet_constraints.append(
                            UnmetConstraint(
                                category="ROM_CONFLICT",
                                target_name=eff_id,
                                description=f"End effector '{eff_id}' cannot satisfy target under anatomical ROM limits (conflict error = {new_pos_err*1000:.2f} mm)",
                                error_amount=new_pos_err,
                            )
                        )

            for side, foot_tgt in leg_targets:
                eff_id = f"foot_{side}"
                if foot_tgt is not None and foot_tgt.enabled:
                    leg_st = get_leg_ik_state(arm, side)
                    new_pos_err = float(leg_st["target_error"])
                    if new_pos_err > tolerance_position_m:
                        unmet_constraints.append(
                            UnmetConstraint(
                                category="ROM_CONFLICT",
                                target_name=eff_id,
                                description=f"End effector '{eff_id}' cannot satisfy target under anatomical ROM limits (conflict error = {new_pos_err*1000:.2f} mm)",
                                error_amount=new_pos_err,
                            )
                        )

        # ---------------------------------------------------------------------
        # 8. Whole-Body Center of Mass (CoM) Evaluation
        # ---------------------------------------------------------------------
        com_result = compute_whole_body_com(arm, self.mass_distribution, update_scene=False)

        # Overall success strictly requires: zero unmet constraints, all reachable, zero ROM violations
        has_rom_viol = not rom_validation.is_valid
        overall_success = (len(unmet_constraints) == 0) and all_reachable and (not has_rom_viol)

        # Positions for telemetry
        root_pos = root.location.to_tuple() if root is not None else (0.0, 0.0, 0.0)
        p_pelvis = arm.pose.bones.get("pelvis")
        pelvis_pos = (arm.matrix_world @ p_pelvis.head).to_tuple() if p_pelvis is not None else (0.0, 0.0, 0.0)

        return WholeBodyControlResult(
            success=overall_success,
            end_effectors=effectors_feedback,
            rom_validation=rom_validation,
            com_result=com_result,
            unmet_constraints=unmet_constraints,
            root_world_position=root_pos,
            pelvis_world_position=pelvis_pos,
            max_end_effector_error_m=max_effector_error,
            has_rom_violation=has_rom_viol,
            is_all_reachable=all_reachable,
        )

    def reset_all_controls(self) -> None:
        """Reset all IK targets, influences, and pose bones back to neutral rest state."""
        reset_arm_ik(self.armature_obj)
        reset_leg_ik(self.armature_obj)
        reset_pose(self.armature_obj)
        bpy.context.view_layer.update()
