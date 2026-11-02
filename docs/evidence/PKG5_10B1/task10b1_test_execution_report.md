# PKG-5 / Task 10-B-1 Test Execution & Regression Evidence Report

> **Task ID**: PKG-5 / Task 10-B-1 (Arm IK 输入预验证与零副作用合同)
>
> **Commit Baseline**: `c8eb01783327654a2cb8b6022b553eadf16ef30b`
>
> **Execution Date**: 2026-11-02
>
> **Environment**: Windows 11 / Blender 5.1.1 / Python 3.11.9
>
> **Acceptance Status**: `TESTED — ARCHIVED — PENDING INDEPENDENT AUDIT`

---

## 1. Archive Inventory

The following evidence logs and reports are archived in `docs/evidence/PKG5_10B1/`:

| Artifact | File Name | Size (Bytes) | Description |
|---|---|---:|---|
| **Execution Report** | [`task10b1_test_execution_report.md`](task10b1_test_execution_report.md) | — | Comprehensive report detailing TEST-01 to TEST-24, 10-A regression, and 4-tier regressions |
| **Specialized Test Log** | [`task10b1_specialized_test.log`](task10b1_specialized_test.log) | 18,052 | Complete console log of `test_task10b_input_validation.py` (24/24 PASS) |
| **10-A Regression Log** | [`task10b1_10a_regression.log`](task10b1_10a_regression.log) | 32,708 | Complete console log of `test_arm_ik_lifecycle_world_transform_contract.py` (30/30 PASS) |
| **Quick Tier Log** | [`task10b1_quick.log`](task10b1_quick.log) | 9,495 | Complete console log of `tests/run_test_suite.py --tier quick` (19/19 PASS) |
| **Physics Tier Log** | [`task10b1_physics.log`](task10b1_physics.log) | 13,105 | Complete console log of `tests/run_test_suite.py --tier physics` (27/27 PASS) |
| **Motion Tier Log** | [`task10b1_motion.log`](task10b1_motion.log) | 6,624 | Complete console log of `tests/run_test_suite.py --tier motion` (12/12 PASS) |
| **Full Tier Log** | [`task10b1_full.log`](task10b1_full.log) | 19,951 | Complete console log of `tests/run_test_suite.py --tier full` (42/42 PASS) |

---

## 2. Itemized Specialized Test Suite Results (TEST-01 to TEST-24)

* **Command**: `& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" -b -P tests/test_task10b_input_validation.py`
* **Test File**: `tests/test_task10b_input_validation.py`
* **Overall Outcome**: **Ran 24 tests in 1.997s — OK (Passed: 24, Failed: 0, Errors: 0, Exit Code: 0)**

| Test ID | Test Method Name | Target Function / Scope | Result | Verification Notes |
|:---|:---|:---:|:---:|:---|
| **TEST-01** | `test_01_setup_accepts_influence_boundaries` | `setup_arm_ik` / Boundaries | **PASS** | Accepts valid boundaries (0.0, 0.5, 1.0, 0, 1) and sets constraint influences correctly. |
| **TEST-02** | `test_02_setup_rejects_non_finite_influence` | `setup_arm_ik` / Non-finite | **PASS** | Rejects NaN, +Inf, -Inf with ValueError. |
| **TEST-03** | `test_03_setup_rejects_influence_below_zero` | `setup_arm_ik` / Lower Bound | **PASS** | Rejects negative values (-0.0001, -0.01, -0.5, -1.0, -100.0) with ValueError. |
| **TEST-04** | `test_04_setup_rejects_influence_above_one` | `setup_arm_ik` / Upper Bound | **PASS** | Rejects excessive values (1.0001, 1.01, 1.5, 2.0, 100.0) with ValueError. |
| **TEST-05** | `test_05_setup_invalid_input_has_zero_scene_mutation` | `setup_arm_ik` / Zero Side-Effect | **PASS** | Zero mutation: no Empties or constraints created on invalid input. |
| **TEST-06** | `test_06_hand_target_rejects_invalid_side` | `set_hand_ik_target` / Side | **PASS** | Rejects invalid side strings, numbers, None, empty collections. |
| **TEST-07** | `test_07_hand_target_rejects_world_xyz_wrong_arity` | `set_hand_ik_target` / Arity | **PASS** | Rejects 0, 1, 2, 4+ element vectors, strings, dicts, None. |
| **TEST-08** | `test_08_hand_target_rejects_world_xyz_non_finite` | `set_hand_ik_target` / Finiteness | **PASS** | Rejects NaN, +Inf, -Inf in coordinates with ValueError. |
| **TEST-09** | `test_09_hand_target_rejects_rotation_wrong_arity` | `set_hand_ik_target` / Rotation Arity | **PASS** | Rejects invalid rotation arity, scalar numbers, strings, booleans, dicts. |
| **TEST-10** | `test_10_hand_target_rejects_rotation_non_finite` | `set_hand_ik_target` / Rotation Finiteness | **PASS** | Rejects NaN, +Inf, -Inf in Euler rotation degrees. |
| **TEST-11** | `test_11_hand_target_rejects_pole_wrong_arity` | `set_hand_ik_target` / Pole Arity | **PASS** | Rejects invalid pole coordinates arity, booleans, strings. |
| **TEST-12** | `test_12_hand_target_rejects_pole_non_finite` | `set_hand_ik_target` / Pole Finiteness | **PASS** | Rejects NaN, +Inf, -Inf in pole coordinates. |
| **TEST-13** | `test_13_hand_target_rejects_non_finite_influence` | `set_hand_ik_target` / Influence Finiteness | **PASS** | Rejects NaN, +Inf, -Inf influence values. |
| **TEST-14** | `test_14_hand_target_rejects_out_of_range_influence` | `set_hand_ik_target` / Influence Range | **PASS** | Rejects influence values < 0.0 or > 1.0. |
| **TEST-15** | `test_15_hand_target_rejects_non_boolean_clamp_reach` | `set_hand_ik_target` / Clamp Type | **PASS** | Strictly rejects non-boolean inputs (0, 1, integers, strings, None) for clamp_reach. |
| **TEST-16** | `test_16_invalid_hand_target_does_not_auto_initialize` | `set_hand_ik_target` / Auto-Init Invariant | **PASS** | Proves uninitialized armature is NOT auto-initialized when inputs are invalid. |
| **TEST-17** | `test_17_invalid_hand_target_leaves_existing_state_unchanged` | `set_hand_ik_target` / State Preservation | **PASS** | Deep snapshot: controllers, bones, constraints, and influences remain identical. |
| **TEST-18** | `test_18_influence_setter_rejects_invalid_side` | `set_arm_ik_influence` / Side | **PASS** | Rejects invalid side identifiers with ValueError / TypeError. |
| **TEST-19** | `test_19_influence_setter_rejects_non_finite_values` | `set_arm_ik_influence` / Finiteness | **PASS** | Rejects NaN, +Inf, -Inf influence values. |
| **TEST-20** | `test_20_influence_setter_rejects_out_of_range_values` | `set_arm_ik_influence` / Range | **PASS** | Rejects influence values < 0.0 or > 1.0. |
| **TEST-21** | `test_21_influence_setter_invalid_input_has_zero_mutation` | `set_arm_ik_influence` / Zero Side-Effect | **PASS** | Rejection does not modify existing L or R influence values. |
| **TEST-22** | `test_22_valid_influence_setter_preserves_left_right_independence` | `set_arm_ik_influence` / Independence | **PASS** | Verifies L/R independence and BOTH updates both arms identically. |
| **TEST-23** | `test_23_valid_hand_target_accepts_boolean_clamp_modes` | `set_hand_ik_target` / Clamp Execution | **PASS** | Both clamp_reach=True and clamp_reach=False execute successfully. |
| **TEST-24** | `test_24_valid_hand_target_preserves_weight_consistency` | `set_hand_ik_target` / Weight Consistency | **PASS** | Sets symmetric influence on both ArmIK and HandRotation constraints. |

---

## 3. Task 10-A Regression Breakdown

* **Command**: `& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" -b -P tests/test_arm_ik_lifecycle_world_transform_contract.py`
* **Test File**: `tests/test_arm_ik_lifecycle_world_transform_contract.py`
* **Execution Count**: **30 test methods**.
* **Failures**: 0.
* **Errors**: 0.
* **Result**: **PASS (30/30)** in 4.439s.

---

## 4. Tiered Regression Suite Results

All four tiers were executed via `tests/run_test_suite.py` without fail-fast:

| Tier | Command | Suite Count | Planned | Executed | Ordinary PASS | AUTOMATED_PASS | FAIL | ERROR | SKIPPED | NOT_RUN | Exit Code | Wall Time |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Quick** | `python tests/run_test_suite.py --tier quick` | 19 | 19 | 19 | 16 | 3 | 0 | 0 | 0 | 0 | **0** | 48.13s |
| **Physics** | `python tests/run_test_suite.py --tier physics` | 27 | 27 | 27 | 24 | 3 | 0 | 0 | 0 | 0 | **0** | 107.51s |
| **Motion** | `python tests/run_test_suite.py --tier motion` | 12 | 12 | 12 | 6 | 6 | 0 | 0 | 0 | 0 | **0** | 48.45s |
| **Full** | `python tests/run_test_suite.py --tier full` | 42 | 42 | 42 | 33 | 9 | 0 | 0 | 0 | 0 | **0** | 158.96s |

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

* Only `src/rig/arm_ik.py` was modified in `src/`.
* Added new test suite `tests/test_task10b_input_validation.py` and registered it in `tests/test_registry.py`.
* Automated regressions were executed fully, including Headless Blender tests (`blender -b`).
* Full Tier includes `dynamics_playground_blend`, which reopens the existing `output/dynamics_playground.blend` in Headless Blender for automated integrity assertions.
* `AUTOMATED_PASS` signifies programmatic check completion only and does not represent user GUI visual acceptance.
* No Blender GUI visual acceptance was performed during this task.
* No manual terrain dragging or real-time character response inspection was performed.
* Bidirectional environment-character interaction visual acceptance remains deferred to subsequent formal phases and Task 6H.
