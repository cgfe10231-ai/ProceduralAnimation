# ProceduralAnimation Test Execution Report

> **Execution Date**: 2026-11-09 23:39:11
> **Target Tier**: `physics`
> **Overall Result**: **ALL PASSED**
> **Execution Summary**: Total Planned: 27 | Executed: 27 | Passed: 27 (Automated Pass: 3) | Failed: 0 | Skipped: 0 (Req: 0, Opt: 0) | Not Run: 0 | Duration: 109.34s

---

## Test Results Table

| Test ID | Test Name | Runner | Status | Duration | Failure / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `dynamics_environment_query` | Dynamics Environment Query & 3D Surface Geometry | `python` | **PASSED** | 0.62s | - |
| `contact_dynamics_math` | Contact Dynamics Foundation & Momentum Impulse | `python` | **PASSED** | 0.63s | - |
| `contact_force_solver` | Multi-Contact Force Solver & Constraint Allocation | `python` | **PASSED** | 0.68s | - |
| `forward_dynamics` | Forward Dynamics Single-Step Integration Kernel | `python` | **PASSED** | 0.6s | - |
| `closed_loop_dynamics` | Multi-Frame Dynamics Closed-Loop Control & State Feedback | `python` | **PASSED** | 1.18s | - |
| `physics_joint_limits` | Anatomical Joint ROM Limit Verification | `blender_headless` | **PASSED** | 1.62s | - |
| `physics_rigid_link_com` | Rigid Link Segments & Whole-Body CoM | `blender_headless` | **PASSED** | 1.64s | - |
| `physics_whole_body_controller` | Whole-Body Controller Coordination & Dispatch | `blender_headless` | **PASSED** | 1.68s | - |
| `physics_arm_ik` | Dual Arm Two-Bone IK & Hand Orientation | `blender_headless` | **PASSED** | 1.58s | - |
| `physics_body_kinematics` | Differential Kinematics & Velocity Tracking | `blender_headless` | **PASSED** | 2.68s | - |
| `physics_body_inertia` | Inertia Tensor & Whole-Body Angular Momentum | `blender_headless` | **PASSED** | 11.48s | - |
| `physics_contact_model` | Multi-Limb Contact Geometry & Support Classification | `blender_headless` | **PASSED** | 22.63s | - |
| `contact_model_geometry_support_contract` | ContactModel Geometry-to-Support Consistency Contract (FIND-R2-05) | `blender_headless` | **PASSED** | 1.89s | - |
| `leg_ik_worldspace_init_reset` | Leg IK Controller World-Space Initialization & Reset Invariant (PKG-5/WS-01) | `blender_headless` | **PASSED** | 2.08s | - |
| `leg_ik_ground_height_contract` | Leg IK Ground-Height Contract & CharacterRoot Decoupling (PKG-5/09-IK-GROUND-A) | `blender_headless` | **PASSED** | 3.64s | - |
| `leg_ik_world_rotation_contract` | Leg IK World Rotation Contract & Controller Lifecycle Closure (PKG-5/09-B) | `blender_headless` | **PASSED** | 3.65s | - |
| `arm_ik_lifecycle_world_transform_contract` | Arm IK Lifecycle & Effective Parent Transform Contract (Task 10-A) | `blender_headless` | **PASSED** | 6.47s | - |
| `arm_ik_input_validation_contract` | Arm IK Input Pre-Validation & Zero-Side-Effect Contract (Task 10-B-1) | `blender_headless` | **PASSED** | 4.41s | - |
| `physics_bridge_contract` | Kinematic Bridge 14-Point Architectural Contract | `blender_headless` | **PASSED** | 23.29s | - |
| `dynamics_playground_blend` | Dynamics Playground Blender Scene Artifact Verification | `blender_headless` | **AUTOMATED_PASS** | 1.54s | Visual Inspection Required |
| `playground_dynamics_states` | Dynamics Playground Real Dynamics State Integration Verification | `blender_headless` | **AUTOMATED_PASS** | 3.17s | Visual Inspection Required |
| `visual_evidence_telemetry` | Dynamics Visual Evidence & Telemetry Coherence Verification | `python` | **AUTOMATED_PASS** | 0.35s | Visual Inspection Required |
| `mesh_environment_query` | Environment Gate 01: Blender Mesh Environment Adapter & Data Authenticity | `blender_headless` | **PASSED** | 4.31s | - |
| `contact_elevation_gap_repro` | Environment Gate 01 Defect Reproduction: KinematicBridge Elevation Gap | `blender_headless` | **PASSED** | 1.9s | - |
| `task7a2_negative_invariance` | Task 7A-2: Terrain Walk Invariance & Negative Physics Verification | `blender_headless` | **PASSED** | 1.66s | - |
| `environment_gate01_unit4` | Environment Gate 01 / Unit 4: Real Mesh Contact Elevation & Consistency | `blender_headless` | **PASSED** | 2.01s | - |
| `environment_gate01_unit4_closure` | Environment Gate 01 / Unit 4: Non-Support Rejection & Analytical Fallback Closure | `blender_headless` | **PASSED** | 1.95s | - |
