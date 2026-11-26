# ProceduralAnimation Test Execution Report

> **Execution Date**: 2026-11-09 23:43:44
> **Target Tier**: `full`
> **Overall Result**: **ALL PASSED**
> **Execution Summary**: Total Planned: 42 | Executed: 42 | Passed: 42 (Automated Pass: 9) | Failed: 0 | Skipped: 0 (Req: 0, Opt: 0) | Not Run: 0 | Duration: 167.82s

---

## Test Results Table

| Test ID | Test Name | Runner | Status | Duration | Failure / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `architecture_integrity_gate` | Architecture Documentation Integrity & Symbol Existence Gate | `python` | **PASSED** | 1.23s | - |
| `spatial_layout_clearance` | Spatial Corridor Clearance & Math Layout | `blender_headless` | **PASSED** | 1.57s | - |
| `dynamics_environment_query` | Dynamics Environment Query & 3D Surface Geometry | `python` | **PASSED** | 0.63s | - |
| `contact_dynamics_math` | Contact Dynamics Foundation & Momentum Impulse | `python` | **PASSED** | 0.6s | - |
| `contact_force_solver` | Multi-Contact Force Solver & Constraint Allocation | `python` | **PASSED** | 0.7s | - |
| `forward_dynamics` | Forward Dynamics Single-Step Integration Kernel | `python` | **PASSED** | 0.62s | - |
| `closed_loop_dynamics` | Multi-Frame Dynamics Closed-Loop Control & State Feedback | `python` | **PASSED** | 1.19s | - |
| `runner_unit_tests` | Test Suite Runner Unit Tests | `python` | **PASSED** | 1.27s | - |
| `physics_joint_limits` | Anatomical Joint ROM Limit Verification | `blender_headless` | **PASSED** | 1.68s | - |
| `physics_rigid_link_com` | Rigid Link Segments & Whole-Body CoM | `blender_headless` | **PASSED** | 1.63s | - |
| `mesh_environment_query` | Environment Gate 01: Blender Mesh Environment Adapter & Data Authenticity | `blender_headless` | **PASSED** | 4.27s | - |
| `task7a2_p0_teleport_regression` | Task 7A-2 P0: Detection & Prevention of Frame 226->227 Teleportation Defect | `blender_headless` | **PASSED** | 2.21s | - |
| `task7a2_negative_invariance` | Task 7A-2: Terrain Walk Invariance & Negative Physics Verification | `blender_headless` | **PASSED** | 1.67s | - |
| `environment_gate01_unit3` | Environment Gate 01 / Unit 3: Real Mesh BVH Integration & Counter-Factual Verification | `blender_headless` | **AUTOMATED_PASS** | 15.4s | Visual Inspection Required |
| `environment_gate01_u3_s1` | Environment Gate 01 / Unit 3-S1: Root Forward Motion Continuity Across Alternating Footsteps | `blender_headless` | **AUTOMATED_PASS** | 4.74s | Visual Inspection Required |
| `environment_gate01_u3_s2` | Environment Gate 01 / Unit 3-S2: Swing-to-Stance Landing Continuity Repair | `blender_headless` | **AUTOMATED_PASS** | 4.72s | Visual Inspection Required |
| `environment_gate01_unit4` | Environment Gate 01 / Unit 4: Real Mesh Contact Elevation & Consistency | `blender_headless` | **PASSED** | 2.02s | - |
| `environment_gate01_unit4_closure` | Environment Gate 01 / Unit 4: Non-Support Rejection & Analytical Fallback Closure | `blender_headless` | **PASSED** | 1.95s | - |
| `terrain_planning_contract` | Terrain Planning Joint Repair: Direction, Seam, and Timebase Contracts | `blender_headless` | **PASSED** | 2.34s | - |
| `physics_whole_body_controller` | Whole-Body Controller Coordination & Dispatch | `blender_headless` | **PASSED** | 1.73s | - |
| `physics_arm_ik` | Dual Arm Two-Bone IK & Hand Orientation | `blender_headless` | **PASSED** | 1.62s | - |
| `physics_body_kinematics` | Differential Kinematics & Velocity Tracking | `blender_headless` | **PASSED** | 2.71s | - |
| `physics_body_inertia` | Inertia Tensor & Whole-Body Angular Momentum | `blender_headless` | **PASSED** | 11.73s | - |
| `physics_contact_model` | Multi-Limb Contact Geometry & Support Classification | `blender_headless` | **PASSED** | 23.06s | - |
| `contact_model_geometry_support_contract` | ContactModel Geometry-to-Support Consistency Contract (FIND-R2-05) | `blender_headless` | **PASSED** | 1.95s | - |
| `leg_ik_worldspace_init_reset` | Leg IK Controller World-Space Initialization & Reset Invariant (PKG-5/WS-01) | `blender_headless` | **PASSED** | 2.15s | - |
| `leg_ik_ground_height_contract` | Leg IK Ground-Height Contract & CharacterRoot Decoupling (PKG-5/09-IK-GROUND-A) | `blender_headless` | **PASSED** | 3.84s | - |
| `leg_ik_world_rotation_contract` | Leg IK World Rotation Contract & Controller Lifecycle Closure (PKG-5/09-B) | `blender_headless` | **PASSED** | 3.67s | - |
| `arm_ik_lifecycle_world_transform_contract` | Arm IK Lifecycle & Effective Parent Transform Contract (Task 10-A) | `blender_headless` | **PASSED** | 6.02s | - |
| `arm_ik_input_validation_contract` | Arm IK Input Pre-Validation & Zero-Side-Effect Contract (Task 10-B-1) | `blender_headless` | **PASSED** | 4.12s | - |
| `physics_bridge_contract` | Kinematic Bridge 14-Point Architectural Contract | `blender_headless` | **PASSED** | 23.16s | - |
| `dynamics_playground_blend` | Dynamics Playground Blender Scene Artifact Verification | `blender_headless` | **AUTOMATED_PASS** | 1.57s | Visual Inspection Required |
| `playground_dynamics_states` | Dynamics Playground Real Dynamics State Integration Verification | `blender_headless` | **AUTOMATED_PASS** | 3.31s | Visual Inspection Required |
| `visual_evidence_telemetry` | Dynamics Visual Evidence & Telemetry Coherence Verification | `python` | **AUTOMATED_PASS** | 0.35s | Visual Inspection Required |
| `contact_elevation_gap_repro` | Environment Gate 01 Defect Reproduction: KinematicBridge Elevation Gap | `blender_headless` | **PASSED** | 1.96s | - |
| `motion_walk_r3b2` | StartStopWalkAction Unified Bridge Regression | `blender_headless` | **PASSED** | 6.03s | - |
| `motion_run_r3b2` | RunAction Unified Bridge Regression | `blender_headless` | **PASSED** | 3.99s | - |
| `motion_sprint_start_r3b2` | SprintStartAction Unified Bridge Regression | `blender_headless` | **PASSED** | 4.81s | - |
| `motion_sprint_brake_r3b2` | SprintBrakeAction Unified Bridge Regression | `blender_headless` | **PASSED** | 2.7s | - |
| `integration_unified_motion` | Unified 462-Frame Motion Pipeline Artifact Verification | `blender_headless` | **AUTOMATED_PASS** | 1.56s | Visual Inspection Required |
| `task7a1_character_playground` | Task 7A-1: 19-Bone Character Integration into DynamicsPlayground & Control Loop | `blender_headless` | **AUTOMATED_PASS** | 2.81s | Visual Inspection Required |
| `task7a2_terrain_traversal` | Task 7A-2: 19-Bone Character Continuous Terrain Traversal in DynamicsPlayground | `blender_headless` | **AUTOMATED_PASS** | 2.53s | Visual Inspection Required |
