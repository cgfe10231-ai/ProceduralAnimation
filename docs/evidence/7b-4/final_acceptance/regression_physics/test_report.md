# ProceduralAnimation Test Execution Report

> **Execution Date**: 2026-11-28 17:04:56  
> **Target Tier**: `physics`  
> **Overall Result**: **FAILED**  
> **Execution Summary**: Total Planned: 27 | Executed: 22 | Passed: 21 (Automated Pass: 2) | Failed: 1 | Skipped: 0 (Req: 0, Opt: 0) | Not Run: 5 | Duration: 96.38s

---

## Test Results Table

| Test ID | Test Name | Runner | Status | Duration | Failure / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `dynamics_environment_query` | Dynamics Environment Query & 3D Surface Geometry | `python` | **PASSED** | 0.54s | - |
| `contact_dynamics_math` | Contact Dynamics Foundation & Momentum Impulse | `python` | **PASSED** | 0.53s | - |
| `contact_force_solver` | Multi-Contact Force Solver & Constraint Allocation | `python` | **PASSED** | 0.63s | - |
| `forward_dynamics` | Forward Dynamics Single-Step Integration Kernel | `python` | **PASSED** | 0.54s | - |
| `closed_loop_dynamics` | Multi-Frame Dynamics Closed-Loop Control & State Feedback | `python` | **PASSED** | 1.13s | - |
| `physics_joint_limits` | Anatomical Joint ROM Limit Verification | `blender_headless` | **PASSED** | 1.73s | - |
| `physics_rigid_link_com` | Rigid Link Segments & Whole-Body CoM | `blender_headless` | **PASSED** | 1.65s | - |
| `physics_whole_body_controller` | Whole-Body Controller Coordination & Dispatch | `blender_headless` | **PASSED** | 1.72s | - |
| `physics_arm_ik` | Dual Arm Two-Bone IK & Hand Orientation | `blender_headless` | **PASSED** | 1.62s | - |
| `physics_body_kinematics` | Differential Kinematics & Velocity Tracking | `blender_headless` | **PASSED** | 2.63s | - |
| `physics_body_inertia` | Inertia Tensor & Whole-Body Angular Momentum | `blender_headless` | **PASSED** | 11.62s | - |
| `physics_contact_model` | Multi-Limb Contact Geometry & Support Classification | `blender_headless` | **PASSED** | 23.69s | - |
| `contact_model_geometry_support_contract` | ContactModel Geometry-to-Support Consistency Contract (FIND-R2-05) | `blender_headless` | **PASSED** | 2.0s | - |
| `leg_ik_worldspace_init_reset` | Leg IK Controller World-Space Initialization & Reset Invariant (PKG-5/WS-01) | `blender_headless` | **PASSED** | 2.07s | - |
| `leg_ik_ground_height_contract` | Leg IK Ground-Height Contract & CharacterRoot Decoupling (PKG-5/09-IK-GROUND-A) | `blender_headless` | **PASSED** | 3.62s | - |
| `leg_ik_world_rotation_contract` | Leg IK World Rotation Contract & Controller Lifecycle Closure (PKG-5/09-B) | `blender_headless` | **PASSED** | 3.51s | - |
| `arm_ik_lifecycle_world_transform_contract` | Arm IK Lifecycle & Effective Parent Transform Contract (Task 10-A) | `blender_headless` | **PASSED** | 5.67s | - |
| `arm_ik_input_validation_contract` | Arm IK Input Pre-Validation & Zero-Side-Effect Contract (Task 10-B-1) | `blender_headless` | **PASSED** | 3.88s | - |
| `physics_bridge_contract` | Kinematic Bridge 14-Point Architectural Contract | `blender_headless` | **PASSED** | 22.71s | - |
| `dynamics_playground_blend` | Dynamics Playground Blender Scene Artifact Verification | `blender_headless` | **AUTOMATED_PASS** | 1.5s | Visual Inspection Required |
| `playground_dynamics_states` | Dynamics Playground Real Dynamics State Integration Verification | `blender_headless` | **AUTOMATED_PASS** | 3.12s | Visual Inspection Required |
| `visual_evidence_telemetry` | Dynamics Visual Evidence & Telemetry Coherence Verification | `python` | <span style='color:red;'>**FAILED**</span> | 0.27s | Process exited with non-zero code 1 |
| `mesh_environment_query` | Environment Gate 01: Blender Mesh Environment Adapter & Data Authenticity | `blender_headless` | <span style='color:orange;'>**NOT_RUN**</span> | 0.0s | Skipped due to fail-fast after failure on 'visual_evidence_telemetry' |
| `contact_elevation_gap_repro` | Environment Gate 01 Defect Reproduction: KinematicBridge Elevation Gap | `blender_headless` | <span style='color:orange;'>**NOT_RUN**</span> | 0.0s | Skipped due to fail-fast after failure on 'visual_evidence_telemetry' |
| `task7a2_negative_invariance` | Task 7A-2: Terrain Walk Invariance & Negative Physics Verification | `blender_headless` | <span style='color:orange;'>**NOT_RUN**</span> | 0.0s | Skipped due to fail-fast after failure on 'visual_evidence_telemetry' |
| `environment_gate01_unit4` | Environment Gate 01 / Unit 4: Real Mesh Contact Elevation & Consistency | `blender_headless` | <span style='color:orange;'>**NOT_RUN**</span> | 0.0s | Skipped due to fail-fast after failure on 'visual_evidence_telemetry' |
| `environment_gate01_unit4_closure` | Environment Gate 01 / Unit 4: Non-Support Rejection & Analytical Fallback Closure | `blender_headless` | <span style='color:orange;'>**NOT_RUN**</span> | 0.0s | Skipped due to fail-fast after failure on 'visual_evidence_telemetry' |

## Failure & Exception Details

### `visual_evidence_telemetry`: Dynamics Visual Evidence & Telemetry Coherence Verification (FAILED)
- **Reason / Note**: Process exited with non-zero code 1
- **Exit Code**: 1
- **Duration**: 0.27s
```
[STDERR]
facts_and_contact_sheet_exist)
Verify contact sheet, animated GIF, validation report, and keyframe stills exist.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\64701\AppData\Local\Packages\openai.codex_2p2nqsd0c76g0\AC\#!sandbox.{22fc9fb0-a52a-4d0f-bf9c-cf6dc8541e66}\Temp\procedural-7b4-5yedmnyl\repo\tests/verify_task6gd_visual_telemetry.py", line 178, in test_05_visual_evidence_artifacts_and_contact_sheet_exist
    self.assertTrue(os.path.isfile(out_sheet), f"Missing {out_sheet}")
    ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: False is not true : Missing C:\Users\64701\AppData\Local\Packages\openai.codex_2p2nqsd0c76g0\AC\#!sandbox.{22fc9fb0-a52a-4d0f-bf9c-cf6dc8541e66}\Temp\procedural-7b4-5yedmnyl\repo\output\evidence\task6gd_c2a\contact_sheet.png

----------------------------------------------------------------------
Ran 5 tests in 0.004s

FAILED (failures=2, errors=3)

```
### `mesh_environment_query`: Environment Gate 01: Blender Mesh Environment Adapter & Data Authenticity (NOT_RUN)
- **Reason / Note**: Skipped due to fail-fast after failure on 'visual_evidence_telemetry'
- **Exit Code**: None
- **Duration**: 0.0s
### `contact_elevation_gap_repro`: Environment Gate 01 Defect Reproduction: KinematicBridge Elevation Gap (NOT_RUN)
- **Reason / Note**: Skipped due to fail-fast after failure on 'visual_evidence_telemetry'
- **Exit Code**: None
- **Duration**: 0.0s
### `task7a2_negative_invariance`: Task 7A-2: Terrain Walk Invariance & Negative Physics Verification (NOT_RUN)
- **Reason / Note**: Skipped due to fail-fast after failure on 'visual_evidence_telemetry'
- **Exit Code**: None
- **Duration**: 0.0s
### `environment_gate01_unit4`: Environment Gate 01 / Unit 4: Real Mesh Contact Elevation & Consistency (NOT_RUN)
- **Reason / Note**: Skipped due to fail-fast after failure on 'visual_evidence_telemetry'
- **Exit Code**: None
- **Duration**: 0.0s
### `environment_gate01_unit4_closure`: Environment Gate 01 / Unit 4: Non-Support Rejection & Analytical Fallback Closure (NOT_RUN)
- **Reason / Note**: Skipped due to fail-fast after failure on 'visual_evidence_telemetry'
- **Exit Code**: None
- **Duration**: 0.0s