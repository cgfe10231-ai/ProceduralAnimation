# ProceduralAnimation Test Execution Report

> **Execution Date**: 2026-11-02 15:42:31  
> **Target Tier**: `full`  
> **Overall Result**: **ALL PASSED**  
> **Execution Summary**: Total Planned: 40 | Executed: 40 | Passed: 40 (Automated Pass: 9) | Failed: 0 | Skipped: 0 (Req: 0, Opt: 0) | Not Run: 0 | Duration: 148.21s

---

## Test Results Table

| Test ID | Test Name | Runner | Status | Duration | Failure / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `architecture_integrity_gate` | Architecture Documentation Integrity & Symbol Existence Gate | `python` | **PASSED** | 0.94s | - |
| `spatial_layout_clearance` | Spatial Corridor Clearance & Math Layout | `blender_headless` | **PASSED** | 1.59s | - |
| `dynamics_environment_query` | Dynamics Environment Query & 3D Surface Geometry | `python` | **PASSED** | 0.62s | - |
| `contact_dynamics_math` | Contact Dynamics Foundation & Momentum Impulse | `python` | **PASSED** | 0.62s | - |
| `contact_force_solver` | Multi-Contact Force Solver & Constraint Allocation | `python` | **PASSED** | 0.72s | - |
| `forward_dynamics` | Forward Dynamics Single-Step Integration Kernel | `python` | **PASSED** | 0.63s | - |
| `closed_loop_dynamics` | Multi-Frame Dynamics Closed-Loop Control & State Feedback | `python` | **PASSED** | 1.2s | - |
| `runner_unit_tests` | Test Suite Runner Unit Tests | `python` | **PASSED** | 1.25s | - |
| `physics_joint_limits` | Anatomical Joint ROM Limit Verification | `blender_headless` | **PASSED** | 1.61s | - |
| `physics_rigid_link_com` | Rigid Link Segments & Whole-Body CoM | `blender_headless` | **PASSED** | 1.63s | - |
| `mesh_environment_query` | Environment Gate 01: Blender Mesh Environment Adapter & Data Authenticity | `blender_headless` | **PASSED** | 4.15s | - |
| `task7a2_p0_teleport_regression` | Task 7A-2 P0: Detection & Prevention of Frame 226->227 Teleportation Defect | `blender_headless` | **PASSED** | 2.17s | - |
| `task7a2_negative_invariance` | Task 7A-2: Terrain Walk Invariance & Negative Physics Verification | `blender_headless` | **PASSED** | 1.67s | - |
| `environment_gate01_unit3` | Environment Gate 01 / Unit 3: Real Mesh BVH Integration & Counter-Factual Verification | `blender_headless` | **AUTOMATED_PASS** | 15.14s | Visual Inspection Required |
| `environment_gate01_u3_s1` | Environment Gate 01 / Unit 3-S1: Root Forward Motion Continuity Across Alternating Footsteps | `blender_headless` | **AUTOMATED_PASS** | 4.68s | Visual Inspection Required |
| `environment_gate01_u3_s2` | Environment Gate 01 / Unit 3-S2: Swing-to-Stance Landing Continuity Repair | `blender_headless` | **AUTOMATED_PASS** | 4.64s | Visual Inspection Required |
| `environment_gate01_unit4` | Environment Gate 01 / Unit 4: Real Mesh Contact Elevation & Consistency | `blender_headless` | **PASSED** | 1.96s | - |
| `environment_gate01_unit4_closure` | Environment Gate 01 / Unit 4: Non-Support Rejection & Analytical Fallback Closure | `blender_headless` | **PASSED** | 1.92s | - |
| `terrain_planning_contract` | Terrain Planning Joint Repair: Direction, Seam, and Timebase Contracts | `blender_headless` | **PASSED** | 2.14s | - |
| `physics_whole_body_controller` | Whole-Body Controller Coordination & Dispatch | `blender_headless` | **PASSED** | 1.69s | - |
| `physics_arm_ik` | Dual Arm Two-Bone IK & Hand Orientation | `blender_headless` | **PASSED** | 1.61s | - |
| `physics_body_kinematics` | Differential Kinematics & Velocity Tracking | `blender_headless` | **PASSED** | 2.35s | - |
| `physics_body_inertia` | Inertia Tensor & Whole-Body Angular Momentum | `blender_headless` | **PASSED** | 11.12s | - |
| `physics_contact_model` | Multi-Limb Contact Geometry & Support Classification | `blender_headless` | **PASSED** | 21.7s | - |
| `contact_model_geometry_support_contract` | ContactModel Geometry-to-Support Consistency Contract (FIND-R2-05) | `blender_headless` | **PASSED** | 1.91s | - |
| `leg_ik_worldspace_init_reset` | Leg IK Controller World-Space Initialization & Reset Invariant (PKG-5/WS-01) | `blender_headless` | **PASSED** | 2.12s | - |
| `leg_ik_ground_height_contract` | Leg IK Ground-Height Contract & CharacterRoot Decoupling (PKG-5/09-IK-GROUND-A) | `blender_headless` | **PASSED** | 3.81s | - |
| `leg_ik_world_rotation_contract` | Leg IK World Rotation Contract & Controller Lifecycle Closure (PKG-5/09-B) | `blender_headless` | **PASSED** | 3.64s | - |
| `physics_bridge_contract` | Kinematic Bridge 14-Point Architectural Contract | `blender_headless` | **PASSED** | 21.65s | - |
| `dynamics_playground_blend` | Dynamics Playground Blender Scene Artifact Verification | `blender_headless` | **AUTOMATED_PASS** | 1.56s | Visual Inspection Required |
| `playground_dynamics_states` | Dynamics Playground Real Dynamics State Integration Verification | `blender_headless` | **AUTOMATED_PASS** | 3.2s | Visual Inspection Required |
| `visual_evidence_telemetry` | Dynamics Visual Evidence & Telemetry Coherence Verification | `python` | **AUTOMATED_PASS** | 0.35s | Visual Inspection Required |
| `contact_elevation_gap_repro` | Environment Gate 01 Defect Reproduction: KinematicBridge Elevation Gap | `blender_headless` | **PASSED** | 1.91s | - |
| `motion_walk_r3b2` | StartStopWalkAction Unified Bridge Regression | `blender_headless` | **PASSED** | 4.41s | - |
| `motion_run_r3b2` | RunAction Unified Bridge Regression | `blender_headless` | **PASSED** | 3.07s | - |
| `motion_sprint_start_r3b2` | SprintStartAction Unified Bridge Regression | `blender_headless` | **PASSED** | 3.59s | - |
| `motion_sprint_brake_r3b2` | SprintBrakeAction Unified Bridge Regression | `blender_headless` | **PASSED** | 2.35s | - |
| `integration_unified_motion` | Unified 462-Frame Motion Pipeline Artifact Verification | `blender_headless` | **AUTOMATED_PASS** | 1.57s | Visual Inspection Required |
| `task7a1_character_playground` | Task 7A-1: 19-Bone Character Integration into DynamicsPlayground & Control Loop | `blender_headless` | **AUTOMATED_PASS** | 2.79s | Visual Inspection Required |
| `task7a2_terrain_traversal` | Task 7A-2: 19-Bone Character Continuous Terrain Traversal in DynamicsPlayground | `blender_headless` | **AUTOMATED_PASS** | 2.53s | Visual Inspection Required |