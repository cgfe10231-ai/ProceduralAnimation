# ProceduralAnimation Test Execution Report

> **Execution Date**: 2026-11-27 22:11:44  
> **Target Tier**: `physics`  
> **Overall Result**: **FAILED**  
> **Execution Summary**: Total Planned: 27 | Executed: 19 | Passed: 18 (Automated Pass: 0) | Failed: 1 | Skipped: 0 (Req: 0, Opt: 0) | Not Run: 8 | Duration: 84.92s

---

## Test Results Table

| Test ID | Test Name | Runner | Status | Duration | Failure / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `dynamics_environment_query` | Dynamics Environment Query & 3D Surface Geometry | `python` | **PASSED** | 0.78s | - |
| `contact_dynamics_math` | Contact Dynamics Foundation & Momentum Impulse | `python` | **PASSED** | 0.86s | - |
| `contact_force_solver` | Multi-Contact Force Solver & Constraint Allocation | `python` | **PASSED** | 0.91s | - |
| `forward_dynamics` | Forward Dynamics Single-Step Integration Kernel | `python` | **PASSED** | 0.94s | - |
| `closed_loop_dynamics` | Multi-Frame Dynamics Closed-Loop Control & State Feedback | `python` | **PASSED** | 1.69s | - |
| `physics_joint_limits` | Anatomical Joint ROM Limit Verification | `blender_headless` | **PASSED** | 1.94s | - |
| `physics_rigid_link_com` | Rigid Link Segments & Whole-Body CoM | `blender_headless` | **PASSED** | 1.91s | - |
| `physics_whole_body_controller` | Whole-Body Controller Coordination & Dispatch | `blender_headless` | **PASSED** | 2.0s | - |
| `physics_arm_ik` | Dual Arm Two-Bone IK & Hand Orientation | `blender_headless` | **PASSED** | 1.88s | - |
| `physics_body_kinematics` | Differential Kinematics & Velocity Tracking | `blender_headless` | **PASSED** | 3.12s | - |
| `physics_body_inertia` | Inertia Tensor & Whole-Body Angular Momentum | `blender_headless` | **PASSED** | 13.51s | - |
| `physics_contact_model` | Multi-Limb Contact Geometry & Support Classification | `blender_headless` | **PASSED** | 28.6s | - |
| `contact_model_geometry_support_contract` | ContactModel Geometry-to-Support Consistency Contract (FIND-R2-05) | `blender_headless` | **PASSED** | 2.27s | - |
| `leg_ik_worldspace_init_reset` | Leg IK Controller World-Space Initialization & Reset Invariant (PKG-5/WS-01) | `blender_headless` | **PASSED** | 2.48s | - |
| `leg_ik_ground_height_contract` | Leg IK Ground-Height Contract & CharacterRoot Decoupling (PKG-5/09-IK-GROUND-A) | `blender_headless` | **PASSED** | 4.46s | - |
| `leg_ik_world_rotation_contract` | Leg IK World Rotation Contract & Controller Lifecycle Closure (PKG-5/09-B) | `blender_headless` | **PASSED** | 4.13s | - |
| `arm_ik_lifecycle_world_transform_contract` | Arm IK Lifecycle & Effective Parent Transform Contract (Task 10-A) | `blender_headless` | **PASSED** | 6.63s | - |
| `arm_ik_input_validation_contract` | Arm IK Input Pre-Validation & Zero-Side-Effect Contract (Task 10-B-1) | `blender_headless` | **PASSED** | 4.62s | - |
| `physics_bridge_contract` | Kinematic Bridge 14-Point Architectural Contract | `blender_headless` | <span style='color:red;'>**FAILED**</span> | 2.19s | Process exited with non-zero code 1 |
| `dynamics_playground_blend` | Dynamics Playground Blender Scene Artifact Verification | `blender_headless` | <span style='color:orange;'>**NOT_RUN**</span> | 0.0s | Skipped due to fail-fast after failure on 'physics_bridge_contract' |
| `playground_dynamics_states` | Dynamics Playground Real Dynamics State Integration Verification | `blender_headless` | <span style='color:orange;'>**NOT_RUN**</span> | 0.0s | Skipped due to fail-fast after failure on 'physics_bridge_contract' |
| `visual_evidence_telemetry` | Dynamics Visual Evidence & Telemetry Coherence Verification | `python` | <span style='color:orange;'>**NOT_RUN**</span> | 0.0s | Skipped due to fail-fast after failure on 'physics_bridge_contract' |
| `mesh_environment_query` | Environment Gate 01: Blender Mesh Environment Adapter & Data Authenticity | `blender_headless` | <span style='color:orange;'>**NOT_RUN**</span> | 0.0s | Skipped due to fail-fast after failure on 'physics_bridge_contract' |
| `contact_elevation_gap_repro` | Environment Gate 01 Defect Reproduction: KinematicBridge Elevation Gap | `blender_headless` | <span style='color:orange;'>**NOT_RUN**</span> | 0.0s | Skipped due to fail-fast after failure on 'physics_bridge_contract' |
| `task7a2_negative_invariance` | Task 7A-2: Terrain Walk Invariance & Negative Physics Verification | `blender_headless` | <span style='color:orange;'>**NOT_RUN**</span> | 0.0s | Skipped due to fail-fast after failure on 'physics_bridge_contract' |
| `environment_gate01_unit4` | Environment Gate 01 / Unit 4: Real Mesh Contact Elevation & Consistency | `blender_headless` | <span style='color:orange;'>**NOT_RUN**</span> | 0.0s | Skipped due to fail-fast after failure on 'physics_bridge_contract' |
| `environment_gate01_unit4_closure` | Environment Gate 01 / Unit 4: Non-Support Rejection & Analytical Fallback Closure | `blender_headless` | <span style='color:orange;'>**NOT_RUN**</span> | 0.0s | Skipped due to fail-fast after failure on 'physics_bridge_contract' |

## Failure & Exception Details

### `physics_bridge_contract`: Kinematic Bridge 14-Point Architectural Contract (FAILED)
- **Reason / Note**: Process exited with non-zero code 1
- **Exit Code**: 1
- **Duration**: 2.19s
```
[STDERR]
Traceback (most recent call last):
  File "C:\Users\64701\OneDrive\Desktop\ProceduralAnimation\tests\verify_task6gc_r3b1_bridge.py", line 880, in run_all_tests
    passed = func()
  File "C:\Users\64701\OneDrive\Desktop\ProceduralAnimation\tests\verify_task6gc_r3b1_bridge.py", line 596, in test_10_variable_dt_and_kinematic_scaling
    assert math.isclose(derived_vy_25fps, 0.5, abs_tol=1e-3), f"Expected 0.5 m/s at dt=0.04, got {derived_vy_25fps}"
           ~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: Expected 0.5 m/s at dt=0.04, got 0.9999990463256836

```
### `dynamics_playground_blend`: Dynamics Playground Blender Scene Artifact Verification (NOT_RUN)
- **Reason / Note**: Skipped due to fail-fast after failure on 'physics_bridge_contract'
- **Exit Code**: None
- **Duration**: 0.0s
### `playground_dynamics_states`: Dynamics Playground Real Dynamics State Integration Verification (NOT_RUN)
- **Reason / Note**: Skipped due to fail-fast after failure on 'physics_bridge_contract'
- **Exit Code**: None
- **Duration**: 0.0s
### `visual_evidence_telemetry`: Dynamics Visual Evidence & Telemetry Coherence Verification (NOT_RUN)
- **Reason / Note**: Skipped due to fail-fast after failure on 'physics_bridge_contract'
- **Exit Code**: None
- **Duration**: 0.0s
### `mesh_environment_query`: Environment Gate 01: Blender Mesh Environment Adapter & Data Authenticity (NOT_RUN)
- **Reason / Note**: Skipped due to fail-fast after failure on 'physics_bridge_contract'
- **Exit Code**: None
- **Duration**: 0.0s
### `contact_elevation_gap_repro`: Environment Gate 01 Defect Reproduction: KinematicBridge Elevation Gap (NOT_RUN)
- **Reason / Note**: Skipped due to fail-fast after failure on 'physics_bridge_contract'
- **Exit Code**: None
- **Duration**: 0.0s
### `task7a2_negative_invariance`: Task 7A-2: Terrain Walk Invariance & Negative Physics Verification (NOT_RUN)
- **Reason / Note**: Skipped due to fail-fast after failure on 'physics_bridge_contract'
- **Exit Code**: None
- **Duration**: 0.0s
### `environment_gate01_unit4`: Environment Gate 01 / Unit 4: Real Mesh Contact Elevation & Consistency (NOT_RUN)
- **Reason / Note**: Skipped due to fail-fast after failure on 'physics_bridge_contract'
- **Exit Code**: None
- **Duration**: 0.0s
### `environment_gate01_unit4_closure`: Environment Gate 01 / Unit 4: Non-Support Rejection & Analytical Fallback Closure (NOT_RUN)
- **Reason / Note**: Skipped due to fail-fast after failure on 'physics_bridge_contract'
- **Exit Code**: None
- **Duration**: 0.0s