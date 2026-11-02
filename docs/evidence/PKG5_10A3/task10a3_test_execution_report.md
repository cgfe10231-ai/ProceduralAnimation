# PKG-5 / Task 10-A-3 Test Execution & Regression Evidence Report

> **Task ID**: PKG-5 / Task 10-A-3 (Arm IK 旋转模式与 Reset 逐项测试覆盖补全)
>
> **Commit Baseline**: `133aa77007711b31dbe4f42903edc796657cd781`
>
> **Execution Date**: 2026-11-02
>
> **Environment**: Windows 11 / Blender 5.1.1 / Python 3.11.9
>
> **Acceptance Status**: `TESTED — ARCHIVED — PENDING INDEPENDENT AUDIT`

---

## 1. Archive Inventory

The following evidence logs and reports are archived in `docs/evidence/PKG5_10A3/`:

| Artifact | File Name | Size (Bytes) | Description |
|---|---|---:|---|
| **Execution Report** | [`task10a3_test_execution_report.md`](task10a3_test_execution_report.md) | — | Comprehensive report detailing TEST-01 to TEST-30 and 4-tier regressions |
| **Specialized Test Log** | [`task10a3_specialized_test.log`](task10a3_specialized_test.log) | 32,708 | Complete console log of `test_arm_ik_lifecycle_world_transform_contract.py` (30/30 PASS) |
| **Quick Tier Log** | [`task10a3_quick.log`](task10a3_quick.log) | 9,496 | Complete console log of `tests/run_test_suite.py --tier quick` (19/19 PASS) |
| **Physics Tier Log** | [`task10a3_physics.log`](task10a3_physics.log) | 12,629 | Complete console log of `tests/run_test_suite.py --tier physics` (26/26 PASS) |
| **Motion Tier Log** | [`task10a3_motion.log`](task10a3_motion.log) | 6,622 | Complete console log of `tests/run_test_suite.py --tier motion` (12/12 PASS) |
| **Full Tier Log** | [`task10a3_full.log`](task10a3_full.log) | 19,469 | Complete console log of `tests/run_test_suite.py --tier full` (41/41 PASS) |

---

## 2. Itemized Specialized Test Suite Results (TEST-01 to TEST-30)

* **Command**: `& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" -b -P tests/test_arm_ik_lifecycle_world_transform_contract.py`
* **Test File**: `tests/test_arm_ik_lifecycle_world_transform_contract.py`
* **Overall Outcome**: **Ran 30 tests in 4.164s — OK (Passed: 30, Failed: 0, Errors: 0, Exit Code: 0)**

| Test ID | Test Method Name | rotation_mode / Scope | Result | Verification Notes |
|:---|:---|:---:|:---:|:---|
| **TEST-01** | `test_01_first_time_initialization` | Lifecycle | **PASS** | Creates 4 Empties and 4 constraints with initial influence. |
| **TEST-02** | `test_02_reinitialization_preserves_controllers` | Lifecycle | **PASS** | Idempotency: preserves controller objects, transforms, parents. |
| **TEST-03** | `test_03_reinitialization_preserves_constraint_instances` | Lifecycle | **PASS** | Idempotency: preserves constraint instances without recreation. |
| **TEST-04** | `test_04_wbc_reconstruction_does_not_reset_arm_ik` | Lifecycle | **PASS** | WBC re-instantiation preserves active arm IK targets & influence. |
| **TEST-05** | `test_05_explicit_reset_contract` | Reset | **PASS** | Explicit reset restores neutral pose and 0.0 influence. |
| **TEST-06** | `test_06_parentless_worldspace_path` | World Transform | **PASS** | Absolute world-space target and pole positioning with `parent=None`. |
| **TEST-07** | `test_07_non_identity_matrix_parent_inverse` | Parent Inversion | **PASS** | Non-identity parent inverse with rotation and scale inverts cleanly. |
| **TEST-08** | `test_08_independent_parent_matrices_for_hand_and_pole` | Parent Matrix | **PASS** | HandIK and ElbowPole with distinct parents resolve independently. |
| **TEST-09** | `test_09_supported_effective_parent_domain` | Domain Math | **PASS** | Supported domain accepts pure rotation, positive uniform scale, translation. |
| **TEST-10** | `test_10_rejected_effective_parent_domain` | Domain Math | **PASS** | Unsupported domain rejects NaN, Inf, non-affine, singular, shear, non-uniform. |
| **TEST-11** | `test_11_rejection_leaves_state_unpolluted` | State Invariant | **PASS** | Phase A rejection leaves controllers, bones, constraints 100% unmutated. |
| **TEST-12** | `test_12_regression_compatibility_leg_ik` | Regression | **PASS** | **Inner suite TestLegIKWorldRotationContract executed: 27/27 PASS**. |
| **TEST-13** | `test_13_effective_parent_stale_depgraph_update` | Depgraph Timing | **PASS** | Un-updated parent transforms refreshed via internal `view_layer.update()`. |
| **TEST-14** | `test_14_rotation_mode_xyz` | Set Target / XYZ | **PASS** | Preserves XYZ mode; position error $\le 10^{-5}$ m, angular error $\le 10^{-4}$ rad. |
| **TEST-15** | `test_15_rotation_mode_xzy` | Set Target / XZY | **PASS** | Preserves XZY mode; position error $\le 10^{-5}$ m, angular error $\le 10^{-4}$ rad. |
| **TEST-16** | `test_16_rotation_mode_yxz` | Set Target / YXZ | **PASS** | Preserves YXZ mode; position error $\le 10^{-5}$ m, angular error $\le 10^{-4}$ rad. |
| **TEST-17** | `test_17_rotation_mode_yzx` | Set Target / YZX | **PASS** | Preserves YZX mode; position error $\le 10^{-5}$ m, angular error $\le 10^{-4}$ rad. |
| **TEST-18** | `test_18_rotation_mode_zxy` | Set Target / ZXY | **PASS** | Preserves ZXY mode; position error $\le 10^{-5}$ m, angular error $\le 10^{-4}$ rad. |
| **TEST-19** | `test_19_rotation_mode_zyx` | Set Target / ZYX | **PASS** | Preserves ZYX mode; position error $\le 10^{-5}$ m, angular error $\le 10^{-4}$ rad. |
| **TEST-20** | `test_20_rotation_mode_quaternion` | Set Target / QUATERNION | **PASS** | Preserves QUATERNION mode; position $\le 10^{-5}$ m, angular error $\le 10^{-4}$ rad. |
| **TEST-21** | `test_21_rotation_mode_axis_angle` | Set Target / AXIS_ANGLE | **PASS** | Preserves AXIS_ANGLE mode; position $\le 10^{-5}$ m, angular error $\le 10^{-4}$ rad. |
| **TEST-22** | `test_22_reset_distinct_non_identity_parent_inverses` | Reset / Distinct Parents | **PASS** | HandIK & ElbowPole have distinct parents/inverses; restores neutral transforms. |
| **TEST-23** | `test_23_reset_rotation_mode_xyz` | Reset / XYZ | **PASS** | Preserves XYZ mode; HandIK/ElbowPole neutral world transform restored. |
| **TEST-24** | `test_24_reset_rotation_mode_xzy` | Reset / XZY | **PASS** | Preserves XZY mode; HandIK/ElbowPole neutral world transform restored. |
| **TEST-25** | `test_25_reset_rotation_mode_yxz` | Reset / YXZ | **PASS** | Preserves YXZ mode; HandIK/ElbowPole neutral world transform restored. |
| **TEST-26** | `test_26_reset_rotation_mode_yzx` | Reset / YZX | **PASS** | Preserves YZX mode; HandIK/ElbowPole neutral world transform restored. |
| **TEST-27** | `test_27_reset_rotation_mode_zxy` | Reset / ZXY | **PASS** | Preserves ZXY mode; HandIK/ElbowPole neutral world transform restored. |
| **TEST-28** | `test_28_reset_rotation_mode_zyx` | Reset / ZYX | **PASS** | Preserves ZYX mode; HandIK/ElbowPole neutral world transform restored. |
| **TEST-29** | `test_29_reset_rotation_mode_quaternion` | Reset / QUATERNION | **PASS** | Preserves QUATERNION mode; HandIK/ElbowPole neutral world transform restored. |
| **TEST-30** | `test_30_reset_rotation_mode_axis_angle` | Reset / AXIS_ANGLE | **PASS** | Preserves AXIS_ANGLE mode; HandIK/ElbowPole neutral world transform restored. |

---

## 3. TEST-12 09-B Leg IK Regression Breakdown

`TEST-12` programmatically loads and executes the complete `TestLegIKWorldRotationContract` suite from `tests/test_leg_ik_world_rotation_contract.py`.
* **Execution Count**: **27 inner test methods**.
* **Failures**: 0.
* **Errors**: 0.
* **Result**: **PASS (27/27)**.
* **Verification**: In addition, the standalone suite runner command `python tests/run_test_suite.py --test-id leg_ik_world_rotation_contract` also verified all 27 tests with Exit Code 0 in 3.88s.

---

## 4. Tiered Regression Suite Results

All four tiers were executed via `tests/run_test_suite.py` without fail-fast, with all suites reporting:

| Tier | Command | Suite Count | Planned | Executed | Ordinary PASS | AUTOMATED_PASS | FAIL | ERROR | SKIPPED | NOT_RUN | Exit Code | Wall Time |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Quick** | `python tests/run_test_suite.py --tier quick` | 19 | 19 | 19 | 16 | 3 | 0 | 0 | 0 | 0 | **0** | 50.55s |
| **Physics** | `python tests/run_test_suite.py --tier physics` | 26 | 26 | 26 | 23 | 3 | 0 | 0 | 0 | 0 | **0** | 115.20s |
| **Motion** | `python tests/run_test_suite.py --tier motion` | 12 | 12 | 12 | 6 | 6 | 0 | 0 | 0 | 0 | **0** | 93.45s |
| **Full** | `python tests/run_test_suite.py --tier full` | 41 | 41 | 41 | 32 | 9 | 0 | 0 | 0 | 0 | **0** | 216.37s |

> **Notice on AUTOMATED_PASS**:
> Automated test passes labeled `AUTOMATED_PASS` (e.g. playground blend visual evidence and terrain traversal suites) indicate that programmatic assertions and invariants hold. They are not equivalent to GUI visual acceptance, which remains deferred to final milestone visual checkpoints.

---

## 5. Documentation & Symbol Integrity

* **Command**: `python tests/audit_c2_final_inspector.py --verify-docs`
* **Output**:
  ```text
  [SELF-TEST] PASS: All 6 validator test cases (Positive, Negative, Proposed, Prose, Dynamic, Clause Exemption) verified successfully.
  [VERIFY-DOCS] PASS: All referenced src/tests paths exist on disk and zero phantom symbols found.
  ```
* **Exit Code**: `0`.

---

## 6. Scope Boundaries & Blend Acceptance Statement

* No files in `src/` were modified.
* No files in `tests/test_arm_ik_lifecycle_world_transform_contract.py` or `tests/test_registry.py` were modified.
* No `.blend` scenes were generated, overwritten, opened, or rendered.
* No manual GUI drag-and-drop or character terrain interaction acceptance was performed.
* Bidirectional environment-character interaction is deferred to subsequent formal tasks and Task 6H.
