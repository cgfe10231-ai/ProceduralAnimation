"""Central Test Registry for ProceduralAnimation (Task 6G-D-PRE-P1).

Provides an explicit, structured registry of all test suites in the repository,
eliminating filename guesswork and establishing strict execution metadata:
- Execution environment (Python vs Headless Blender vs Blend Reopen)
- Multi-tier categorization (quick, physics, motion, full, legacy)
- Per-test timeout limits and child process management
- Preservation of historical regression baselines
- Separation of Automated Pass vs Visual Inspection Required
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set


class RunnerType(str, Enum):
    PYTHON = "python"                          # Pure Python execution (sys.executable)
    BLENDER_HEADLESS = "blender_headless"      # Headless Blender: blender -b -P <script>
    BLENDER_WITH_BLEND = "blender_with_blend"  # Headless Blender loading blend first: blender -b <blend> -P <script>


class TestTier(str, Enum):
    QUICK = "quick"        # Fast smoke checks (Python spatial/clearance + in-memory ROM/CoM, ~5s)
    PHYSICS = "physics"    # Core kinematic, dynamic and constraint math modules (~45s)
    MOTION = "motion"      # Locomotion action regressions (Walk, Run, SprintStart, SprintBrake, Unified) (~60s)
    FULL = "full"          # Comprehensive deduplicated union of active test suites (~120s)
    LEGACY = "legacy"      # Historical prototype and baseline artifact inspection tests


@dataclass
class TestDefinition:
    """Explicit metadata definition for an individual test script."""
    test_id: str
    name: str
    script_path: str
    runner_type: RunnerType
    tiers: List[TestTier]
    timeout_sec: float = 60.0
    target_blend: Optional[str] = None
    expected_artifacts: List[str] = field(default_factory=list)
    creates_artifacts: bool = False
    overwrites_history: bool = False
    is_visual_acceptance: bool = False
    is_optional: bool = False
    description: str = ""
    script_args: List[str] = field(default_factory=list)

    def validate(self, project_root: str) -> List[str]:
        """Validate definition integrity against local file system."""
        errors = []
        full_script = os.path.join(project_root, self.script_path)
        if not os.path.isfile(full_script):
            errors.append(f"Script path not found: {self.script_path}")
        if self.runner_type == RunnerType.BLENDER_WITH_BLEND:
            if not self.target_blend:
                errors.append(f"Test '{self.test_id}' uses BLENDER_WITH_BLEND but has no target_blend specified.")
            else:
                full_blend = os.path.join(project_root, self.target_blend)
                if not os.path.isfile(full_blend):
                    errors.append(f"Target blend file not found: {self.target_blend}")
        return errors


# =============================================================================
# Explicit Test Registry Definitions
# =============================================================================

TEST_REGISTRY: Dict[str, TestDefinition] = {
    # -------------------------------------------------------------------------
    # Tier 1: Quick Smoke Checks (Pure Python + Fast In-Memory)
    # -------------------------------------------------------------------------
    "architecture_integrity_gate": TestDefinition(
        test_id="architecture_integrity_gate",
        name="Architecture Documentation Integrity & Symbol Existence Gate",
        script_path="tests/test_architecture_integrity_gate.py",
        runner_type=RunnerType.PYTHON,
        tiers=[TestTier.QUICK, TestTier.FULL],
        timeout_sec=15.0,
        description="Strictly read-only AST existence check across all architecture freeze docs.",
    ),
    "spatial_layout_clearance": TestDefinition(
        test_id="spatial_layout_clearance",
        name="Spatial Corridor Clearance & Math Layout",
        script_path="tests/test_task3_spatial.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.QUICK, TestTier.FULL, TestTier.LEGACY],
        timeout_sec=15.0,
        description="Validates procedural layout generator, clearance buffers, and corridor math in headless Blender.",
    ),
    "dynamics_environment_query": TestDefinition(
        test_id="dynamics_environment_query",
        name="Dynamics Environment Query & 3D Surface Geometry",
        script_path="tests/verify_task6gd_dynamics_playground.py",
        runner_type=RunnerType.PYTHON,
        tiers=[TestTier.QUICK, TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=15.0,
        description="Validates closed-form 3D surface queries, normal vectors, signed distance, step/slope/wall geometry, and EnvironmentQuery compatibility.",
    ),
    "contact_dynamics_math": TestDefinition(
        test_id="contact_dynamics_math",
        name="Contact Dynamics Foundation & Momentum Impulse",
        script_path="tests/verify_task6gd_contact_dynamics.py",
        runner_type=RunnerType.PYTHON,
        tiers=[TestTier.QUICK, TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=15.0,
        description="Validates 3D contact forces, torques about CoM, linear/angular impulses, Coulomb friction cone, and playground contract.",
    ),
    "contact_force_solver": TestDefinition(
        test_id="contact_force_solver",
        name="Multi-Contact Force Solver & Constraint Allocation",
        script_path="tests/verify_task6gd_contact_force_solver.py",
        runner_type=RunnerType.PYTHON,
        tiers=[TestTier.QUICK, TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=30.0,
        description="Validates multi-contact force solver, QP/SPG contact wrench allocation, friction cone constraints, DynamicsPlayground integration, and feasibility detection.",
    ),
    "forward_dynamics": TestDefinition(
        test_id="forward_dynamics",
        name="Forward Dynamics Single-Step Integration Kernel",
        script_path="tests/verify_task6gd_forward_dynamics.py",
        runner_type=RunnerType.PYTHON,
        tiers=[TestTier.QUICK, TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=15.0,
        description="Validates 6-DOF forward dynamics single-step kernel, Newton-Euler equations, momentum/angular momentum integration, quaternion attitude updates, and failure atomicity.",
    ),
    "closed_loop_dynamics": TestDefinition(
        test_id="closed_loop_dynamics",
        name="Multi-Frame Dynamics Closed-Loop Control & State Feedback",
        script_path="tests/verify_task6gd_closed_loop_dynamics.py",
        runner_type=RunnerType.PYTHON,
        tiers=[TestTier.QUICK, TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=30.0,
        description="Validates multi-frame closed-loop coordination, target wrench feedback, solver admissibility gating, Newton-Euler forward integration, and deterministic trajectory reproducibility.",
    ),
    "runner_unit_tests": TestDefinition(
        test_id="runner_unit_tests",
        name="Test Suite Runner Unit Tests",
        script_path="tests/test_runner_unit.py",
        runner_type=RunnerType.PYTHON,
        tiers=[TestTier.QUICK, TestTier.FULL],
        timeout_sec=30.0,
        description="Comprehensive unit tests for the test runner: failures, timeouts, fail-fast, skipped, NOT_RUN, and artifact validation.",
    ),
    "physics_joint_limits": TestDefinition(
        test_id="physics_joint_limits",
        name="Anatomical Joint ROM Limit Verification",
        script_path="tests/verify_task6fc_joint_limits.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.QUICK, TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=45.0,
        description="Validates 14 joint limits, Euler/cone limits, clamping, and conflict detection.",
    ),
    "physics_rigid_link_com": TestDefinition(
        test_id="physics_rigid_link_com",
        name="Rigid Link Segments & Whole-Body CoM",
        script_path="tests/verify_task6fb_rigid_link.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.QUICK, TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=45.0,
        description="Validates 15 Dempster-Winter segments and forward-kinematic mass-weighted CoM position.",
    ),

    # -------------------------------------------------------------------------
    # Tier 2: Physics & Kinematic Subsystems
    # -------------------------------------------------------------------------
    "physics_whole_body_controller": TestDefinition(
        test_id="physics_whole_body_controller",
        name="Whole-Body Controller Coordination & Dispatch",
        script_path="tests/verify_task6fd_whole_body_controller.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=60.0,
        description="Validates WBC single-frame posture solve, arm/leg IK dispatch, and exclusive ownership.",
    ),
    "physics_arm_ik": TestDefinition(
        test_id="physics_arm_ik",
        name="Dual Arm Two-Bone IK & Hand Orientation",
        script_path="tests/verify_task6fa_arm_ik.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=45.0,
        description="Validates arm IK reachability, wrist sub-millimeter tracking, and 3D orientation alignment.",
    ),
    "physics_body_kinematics": TestDefinition(
        test_id="physics_body_kinematics",
        name="Differential Kinematics & Velocity Tracking",
        script_path="tests/verify_task6ga_body_kinematics.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=60.0,
        description="Validates finite-difference linear/angular velocities and accelerations for root, pelvis, CoM.",
    ),
    "physics_body_inertia": TestDefinition(
        test_id="physics_body_inertia",
        name="Inertia Tensor & Whole-Body Angular Momentum",
        script_path="tests/verify_task6gb_body_inertia.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=60.0,
        description="Validates 3D parallel axis inertia tensor synthesis and spin/orbital angular momentum decoupling.",
    ),
    "physics_contact_model": TestDefinition(
        test_id="physics_contact_model",
        name="Multi-Limb Contact Geometry & Support Classification",
        script_path="tests/verify_task6gc_contact_model.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=90.0,
        description="Validates contact gap, penetration, slip, lifecycle state machine, and 8 support categories.",
    ),
    "physics_bridge_contract": TestDefinition(
        test_id="physics_bridge_contract",
        name="Kinematic Bridge 14-Point Architectural Contract",
        script_path="tests/verify_task6gc_r3b1_bridge.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=120.0,
        description="Full 14-test regression verifying lossless mapping, ownership, dt scaling, and 6 core modules.",
    ),
    "dynamics_playground_blend": TestDefinition(
        test_id="dynamics_playground_blend",
        name="Dynamics Playground Blender Scene Artifact Verification",
        script_path="tests/verify_task6gd_playground_blend.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=45.0,
        expected_artifacts=["output/dynamics_playground.blend"],
        is_visual_acceptance=True,
        description="Reopens dynamics_playground.blend in headless Blender to verify 6-zone meshes, materials, normal arrows, and cameras.",
    ),
    "playground_dynamics_states": TestDefinition(
        test_id="playground_dynamics_states",
        name="Dynamics Playground Real Dynamics State Integration Verification",
        script_path="tests/verify_task6gd_playground_dynamics.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=45.0,
        expected_artifacts=["output/dynamics_playground.blend"],
        is_visual_acceptance=True,
        description="Verifies 5-scenario real dynamics states, CoM trajectories, dynamic force arrows, and attitude keyframes in dynamics_playground.blend.",
    ),
    "visual_evidence_telemetry": TestDefinition(
        test_id="visual_evidence_telemetry",
        name="Dynamics Visual Evidence & Telemetry Coherence Verification",
        script_path="tests/verify_task6gd_visual_telemetry.py",
        runner_type=RunnerType.PYTHON,
        tiers=[TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=45.0,
        expected_artifacts=[
            "output/evidence/task6gd_c2a/telemetry.json",
            "docs/evidence/task6gd_c2a/telemetry.json",
            "docs/evidence/task6gd_c2a/contact_sheet.png",
            "docs/evidence/task6gd_c2a/validation_report.md",
        ],
        is_visual_acceptance=True,
        description="Verifies frame-by-frame physics and object telemetry coherence, contact force fidelity, anti-spoofing divergence, contact sheet, and validation report existence.",
    ),
    "mesh_environment_query": TestDefinition(
        test_id="mesh_environment_query",
        name="Environment Gate 01: Blender Mesh Environment Adapter & Data Authenticity",
        script_path="tests/test_mesh_environment_query.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.QUICK, TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=45.0,
        description="Comprehensive 14-point regression verifying BlenderMeshEnvironmentAdapter, BVHTree spatial queries, dynamic mesh mutations, support classification, and friction metadata.",
    ),
    "contact_elevation_gap_repro": TestDefinition(
        test_id="contact_elevation_gap_repro",
        name="Environment Gate 01 Defect Reproduction: KinematicBridge Elevation Gap",
        script_path="tests/test_contact_elevation_gap_repro.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=45.0,
        description="Demonstrates and verifies the stance contact Z=0.0 flattening defect in KinematicBridge line 404.",
    ),

    # -------------------------------------------------------------------------
    # Tier 3: Locomotion Actions & Unified Motion Integration
    # -------------------------------------------------------------------------
    "motion_walk_r3b2": TestDefinition(
        test_id="motion_walk_r3b2",
        name="StartStopWalkAction Unified Bridge Regression",
        script_path="tests/verify_r3b2_walk_action.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.MOTION, TestTier.FULL],
        timeout_sec=60.0,
        description="Validates 204-frame walk and 408-frame chained walk via KinematicBridgeExecutor.",
    ),
    "motion_run_r3b2": TestDefinition(
        test_id="motion_run_r3b2",
        name="RunAction Unified Bridge Regression",
        script_path="tests/verify_r3b2_run_action.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.MOTION, TestTier.FULL],
        timeout_sec=60.0,
        description="Validates 96-frame run and 252-frame chained walk->run with 40 airborne frames and -38 deg ankle pitch.",
    ),
    "motion_sprint_start_r3b2": TestDefinition(
        test_id="motion_sprint_start_r3b2",
        name="SprintStartAction Unified Bridge Regression",
        script_path="tests/verify_r3b2_sprint_start.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.MOTION, TestTier.FULL],
        timeout_sec=60.0,
        description="Validates 114-frame sprint start burst with 49 airborne frames and -36 deg ankle pitch.",
    ),
    "motion_sprint_brake_r3b2": TestDefinition(
        test_id="motion_sprint_brake_r3b2",
        name="SprintBrakeAction Unified Bridge Regression",
        script_path="tests/verify_r3b2_sprint_brake.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.MOTION, TestTier.FULL],
        timeout_sec=60.0,
        description="Validates 162-frame chained sprint->brake with active deceleration to bilateral stop.",
    ),
    "integration_unified_motion": TestDefinition(
        test_id="integration_unified_motion",
        name="Unified 462-Frame Motion Pipeline Artifact Verification",
        script_path="tests/verify_unified_motion_integration.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.MOTION, TestTier.FULL],
        timeout_sec=60.0,
        expected_artifacts=["output/unified_motion_integration.blend"],
        is_visual_acceptance=True,
        description="Reopens unified_motion_integration.blend to verify root progression, bone bounds, and keyframes.",
    ),
    "task7a1_character_playground": TestDefinition(
        test_id="task7a1_character_playground",
        name="Task 7A-1: 19-Bone Character Integration into DynamicsPlayground & Control Loop",
        script_path="tests/verify_task7a1_character_playground.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.MOTION, TestTier.FULL],
        timeout_sec=90.0,
        expected_artifacts=[
            "output/dynamics_playground.blend",
            "output/dynamics_playground_task7a1.blend",
            "docs/evidence/task7a1/full_frame_validation.json",
            "docs/evidence/task7a1/task7a1_verification_report.json",
            "docs/evidence/task7a1/task7a1_walk_preview.gif",
        ],
        is_visual_acceptance=True,
        description="Read-only reopen verification of 19-bone character integration into DynamicsPlayground, 204-frame mathematical/continuity/contact validation, deep scene preservation, and 204-frame continuous GIF.",
    ),
    "task7a2_p0_teleport_regression": TestDefinition(
        test_id="task7a2_p0_teleport_regression",
        name="Task 7A-2 P0: Detection & Prevention of Frame 226->227 Teleportation Defect",
        script_path="tests/test_p0_frame226_teleport_regression.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.QUICK, TestTier.MOTION, TestTier.FULL],
        timeout_sec=30.0,
        expected_artifacts=[
            "output/dynamics_playground_task7a2.blend",
            "output/dynamics_playground_task7a2_corrected.blend",
        ],
        description="Regression test proving detection of the 2.37m teleportation defect in baseline blend and 0-violation unexempted continuity in corrected blend.",
    ),
    "task7a2_negative_invariance": TestDefinition(
        test_id="task7a2_negative_invariance",
        name="Task 7A-2: Terrain Walk Invariance & Negative Physics Verification",
        script_path="tests/test_terrain_walk_negative.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.QUICK, TestTier.PHYSICS, TestTier.FULL],
        timeout_sec=20.0,
        description="Negative tests proving 100% surface renaming invariance, dynamic elevation perturbation adaptation, and physiological drop rejection (>0.35m).",
    ),
    "task7a2_terrain_traversal": TestDefinition(
        test_id="task7a2_terrain_traversal",
        name="Task 7A-2: 19-Bone Character Continuous Terrain Traversal in DynamicsPlayground",
        script_path="tests/verify_task7a2_terrain_traversal.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.MOTION, TestTier.FULL],
        timeout_sec=120.0,
        expected_artifacts=[
            "output/dynamics_playground.blend",
            "output/dynamics_playground_task7a2.blend",
            "output/dynamics_playground_task7a2_corrected.blend",
            "docs/evidence/task7a2/task7a2_contact_state_records.json",
            "docs/evidence/task7a2/task7a2_execution_summary.json",
            "docs/evidence/task7a2/task7a2_control_chain_diagnostics.json",
            "docs/evidence/task7a2/task7a2_validation_report.json",
            "docs/evidence/task7a2/task7a2_evidence_manifest.json",
            "docs/evidence/task7a2/task7a2_ramp_traversal.gif",
            "docs/evidence/task7a2/task7a2_control_chain_debug.gif",
        ],
        is_visual_acceptance=True,
        description="Read-only verification of 19-bone character continuous terrain traversal in DynamicsPlayground, 700-frame mathematical evaluation, zero ROM violations, zero ankle drift, dedicated diagnostic scene, and visual evidence.",
    ),
    "environment_gate01_unit3": TestDefinition(
        test_id="environment_gate01_unit3",
        name="Environment Gate 01 / Unit 3: Real Mesh BVH Integration & Counter-Factual Verification",
        script_path="tests/test_environment_gate01_unit3.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.QUICK, TestTier.MOTION, TestTier.FULL],
        timeout_sec=60.0,
        expected_artifacts=[
            "output/dynamics_playground.blend",
            "output/dynamics_playground_environment_gate01_u3.blend",
            "output/dynamics_playground_environment_gate01_u3_perturbed.blend",
            "docs/evidence/environment_gate01_ru3/u3_contact_state_records.json",
            "docs/evidence/environment_gate01_ru3/u3_execution_summary.json",
            "docs/evidence/environment_gate01_ru3/u3_control_chain_diagnostics.json",
            "docs/evidence/environment_gate01_ru3/u3_perturbed_contact_state_records.json",
            "docs/evidence/environment_gate01_ru3/u3_perturbed_execution_summary.json",
            "docs/evidence/environment_gate01_ru3/u3_perturbed_control_chain_diagnostics.json",
        ],
        is_visual_acceptance=True,
        description="Comprehensive 14-point regression verifying real mesh BVH environment query injection, single-hit consistency, strict no-support rejection, 6-phase pipeline preservation, counter-factual perturbation sensitivity, and 700-frame unexempted continuity.",
    ),
    "environment_gate01_u3_s1": TestDefinition(
        test_id="environment_gate01_u3_s1",
        name="Environment Gate 01 / Unit 3-S1: Root Forward Motion Continuity Across Alternating Footsteps",
        script_path="tests/test_environment_gate01_u3_s1.py",
        runner_type=RunnerType.BLENDER_HEADLESS,
        tiers=[TestTier.QUICK, TestTier.MOTION, TestTier.FULL],
        timeout_sec=60.0,
        expected_artifacts=[
            "output/dynamics_playground_environment_gate01_u3_s1.blend",
            "docs/evidence/environment_gate01_u3_s1/root_velocity_before.csv",
            "docs/evidence/environment_gate01_u3_s1/root_velocity_after.csv",
            "docs/evidence/environment_gate01_u3_s1/root_acceleration_after.csv",
            "docs/evidence/environment_gate01_u3_s1/root_step_boundary_report.json",
            "docs/evidence/environment_gate01_u3_s1/root_continuity_comparison.json",
            "docs/evidence/environment_gate01_u3_s1/u3_s1_visual_review.md",
        ],
        is_visual_acceptance=True,
        description="Verifies decoupling of Root forward motion from single-step swing foot interpolation, elimination of boundary velocity collapse, 0 ROM violations, and foot contact preservation.",
    ),

    # -------------------------------------------------------------------------
    # Tier 4: Legacy & Historical Baseline Artifact Inspection
    # -------------------------------------------------------------------------
    "legacy_start_stop_walk": TestDefinition(
        test_id="legacy_start_stop_walk",
        name="Historical Start-Stop Walk Artifact Verification",
        script_path="tests/verify_task5c_start_stop_walk.py",
        runner_type=RunnerType.BLENDER_WITH_BLEND,
        target_blend="output/character_start_stop_walk.blend",
        expected_artifacts=["output/character_start_stop_walk.blend"],
        tiers=[TestTier.LEGACY],
        timeout_sec=60.0,
        description="Reopens character_start_stop_walk.blend to verify historical Task 5C step progression.",
    ),
    "legacy_forward_walk": TestDefinition(
        test_id="legacy_forward_walk",
        name="Historical Forward Walk Artifact Verification",
        script_path="tests/verify_task5b_forward_walk.py",
        runner_type=RunnerType.BLENDER_WITH_BLEND,
        target_blend="output/character_forward_walk.blend",
        expected_artifacts=["output/character_forward_walk.blend"],
        tiers=[TestTier.LEGACY],
        timeout_sec=60.0,
        description="Reopens character_forward_walk.blend to verify historical Task 5B 4-step forward walk.",
    ),
    "legacy_walk_cycle": TestDefinition(
        test_id="legacy_walk_cycle",
        name="Historical In-Place Walk Cycle Artifact Verification",
        script_path="tests/verify_task5a_walk_cycle.py",
        runner_type=RunnerType.BLENDER_WITH_BLEND,
        target_blend="output/character_walk_cycle.blend",
        expected_artifacts=["output/character_walk_cycle.blend"],
        tiers=[TestTier.LEGACY],
        timeout_sec=45.0,
        description="Reopens character_walk_cycle.blend to verify historical Task 5A in-place gait cycles.",
    ),
    "legacy_run": TestDefinition(
        test_id="legacy_run",
        name="Historical Run Prototype Artifact Verification",
        script_path="tests/verify_task6b_run.py",
        runner_type=RunnerType.BLENDER_WITH_BLEND,
        target_blend="output/character_run_prototype.blend",
        expected_artifacts=["output/character_run_prototype.blend"],
        tiers=[TestTier.LEGACY],
        timeout_sec=60.0,
        description="Reopens character_run_prototype.blend to verify historical Task 6B running actions.",
    ),
    "legacy_sprint_start": TestDefinition(
        test_id="legacy_sprint_start",
        name="Historical Sprint Start Prototype Artifact Verification",
        script_path="tests/verify_task6c_sprint_start.py",
        runner_type=RunnerType.BLENDER_WITH_BLEND,
        target_blend="output/character_sprint_start_prototype.blend",
        expected_artifacts=["output/character_sprint_start_prototype.blend"],
        tiers=[TestTier.LEGACY],
        timeout_sec=60.0,
        description="Reopens character_sprint_start_prototype.blend to verify historical Task 6C burst.",
    ),
    "legacy_sprint_brake": TestDefinition(
        test_id="legacy_sprint_brake",
        name="Historical Sprint Brake Prototype Artifact Verification",
        script_path="tests/verify_task6d_sprint_brake.py",
        runner_type=RunnerType.BLENDER_WITH_BLEND,
        target_blend="output/character_sprint_brake_prototype.blend",
        expected_artifacts=["output/character_sprint_brake_prototype.blend"],
        tiers=[TestTier.LEGACY],
        timeout_sec=60.0,
        description="Reopens character_sprint_brake_prototype.blend to verify historical Task 6D braking.",
    ),
    "legacy_leg_ik": TestDefinition(
        test_id="legacy_leg_ik",
        name="Historical Leg IK Prototype Artifact Verification",
        script_path="tests/verify_task4c_ik.py",
        runner_type=RunnerType.BLENDER_WITH_BLEND,
        target_blend="output/character_ik_prototype.blend",
        expected_artifacts=["output/character_ik_prototype.blend"],
        tiers=[TestTier.LEGACY],
        timeout_sec=45.0,
        description="Reopens character_ik_prototype.blend to verify historical Task 4C two-bone leg IK.",
    ),
    "legacy_foot_contact": TestDefinition(
        test_id="legacy_foot_contact",
        name="Historical Foot Contact Prototype Artifact Verification",
        script_path="tests/verify_task4d_foot_contact.py",
        runner_type=RunnerType.BLENDER_WITH_BLEND,
        target_blend="output/character_foot_contact_prototype.blend",
        expected_artifacts=["output/character_foot_contact_prototype.blend"],
        tiers=[TestTier.LEGACY],
        timeout_sec=45.0,
        description="Reopens character_foot_contact_prototype.blend to verify Task 4D foot locking.",
    ),
    "legacy_rig": TestDefinition(
        test_id="legacy_rig",
        name="Historical Character Rig Prototype Artifact Verification",
        script_path="tests/verify_task4b_rig.py",
        runner_type=RunnerType.BLENDER_WITH_BLEND,
        target_blend="output/character_rig_prototype.blend",
        expected_artifacts=["output/character_rig_prototype.blend"],
        tiers=[TestTier.LEGACY],
        timeout_sec=45.0,
        description="Reopens character_rig_prototype.blend to verify Task 4B 19-bone hierarchy.",
    ),
    "legacy_character": TestDefinition(
        test_id="legacy_character",
        name="Historical Character Mesh Prototype Artifact Verification",
        script_path="tests/verify_task4a_character.py",
        runner_type=RunnerType.BLENDER_WITH_BLEND,
        target_blend="output/character_prototype.blend",
        expected_artifacts=["output/character_prototype.blend"],
        tiers=[TestTier.LEGACY],
        timeout_sec=45.0,
        description="Reopens character_prototype.blend to verify Task 4A 13-part placeholder mesh.",
    ),
    "legacy_motion_framework": TestDefinition(
        test_id="legacy_motion_framework",
        name="Historical Motion Framework 5C Artifact Verification",
        script_path="tests/verify_task6a_motion_framework.py",
        runner_type=RunnerType.BLENDER_WITH_BLEND,
        target_blend="output/character_motion_framework_5c.blend",
        expected_artifacts=["output/character_motion_framework_5c.blend"],
        tiers=[TestTier.LEGACY],
        timeout_sec=45.0,
        description="Reopens character_motion_framework_5c.blend to verify Task 6A initial state flow.",
    ),
    "legacy_scene_task3": TestDefinition(
        test_id="legacy_scene_task3",
        name="Historical Task 3 Scene Layout Artifact Verification",
        script_path="tests/verify_task3_blend.py",
        runner_type=RunnerType.BLENDER_WITH_BLEND,
        target_blend="output/procedural_scene.blend",
        expected_artifacts=["output/procedural_scene.blend"],
        tiers=[TestTier.LEGACY],
        timeout_sec=30.0,
        description="Reopens procedural_scene.blend to verify Task 3 environment objects and ground slab.",
    ),
}


# =============================================================================
# Helper Queries
# =============================================================================

def get_tests_for_tier(tier: TestTier) -> List[TestDefinition]:
    """Retrieve an ordered, deduplicated list of tests belonging to a designated tier.
    
    If tier is FULL, returns the deduplicated union of active tests:
    QUICK + PHYSICS + MOTION (excluding non-migrated historical blend reopens).
    """
    if tier == TestTier.FULL:
        # Ordered union: quick -> physics -> motion
        seen: Set[str] = set()
        full_list: List[TestDefinition] = []
        for target_tier in [TestTier.QUICK, TestTier.PHYSICS, TestTier.MOTION]:
            for test in TEST_REGISTRY.values():
                if target_tier in test.tiers and test.test_id not in seen:
                    seen.add(test.test_id)
                    full_list.append(test)
        return full_list

    return [test for test in TEST_REGISTRY.values() if tier in test.tiers]


def get_all_registered_tests() -> List[TestDefinition]:
    """Return all registered tests across all categories."""
    return list(TEST_REGISTRY.values())


def find_test_by_id(test_id: str) -> Optional[TestDefinition]:
    """Look up a test definition by its unique test_id."""
    return TEST_REGISTRY.get(test_id)
