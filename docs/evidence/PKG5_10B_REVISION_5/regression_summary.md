# Task 10-B-5: Full Regression Summary Report

## 1. Regression Suite Execution Summary

All tests executed via official runners without bypass. All subtests passed with exit code 0.

| Test Suite / Tier | Execution Command | Planned | Executed | Passed | Failed | Status | Evidence Log |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Task 10-B Input Validation** | `blender.exe -b -P tests/test_task10b_input_validation.py` | 30 | 30 | 30 | 0 | **PASS** | [`01_task10b_input_validation.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/PKG5_10B_REVISION_5/01_task10b_input_validation.log) |
| **Task 10-B Transaction Atomicity** | `blender.exe -b -P tests/test_task10b_transaction_atomicity.py` | 46 | 46 | 46 | 0 | **PASS** | [`02_task10b_transaction_atomicity.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/PKG5_10B_REVISION_5/02_task10b_transaction_atomicity.log) |
| **Task 10-A Regression Suite** | `blender.exe -b -P tests/test_arm_ik_lifecycle_world_transform_contract.py` | 30 | 30 | 30 | 0 | **PASS** | [`03_task10a_regression.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/PKG5_10B_REVISION_5/03_task10a_regression.log) |
| **Tier QUICK** | `.\run_tests.ps1 -tier quick` | 19 | 19 | 19 | 0 | **PASS** | [`04_tier_quick.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/PKG5_10B_REVISION_5/04_tier_quick.log) |
| **Tier PHYSICS** | `.\run_tests.ps1 -tier physics` | 27 | 27 | 27 | 0 | **PASS** | [`05_tier_physics.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/PKG5_10B_REVISION_5/05_tier_physics.log) |
| **Tier MOTION** | `.\run_tests.ps1 -tier motion` | 12 | 12 | 12 | 0 | **PASS** | [`06_tier_motion.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/PKG5_10B_REVISION_5/06_tier_motion.log) |
| **Tier FULL** | `.\run_tests.ps1 -tier full` | 42 | 42 | 42 | 0 | **PASS** | [`07_tier_full.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/PKG5_10B_REVISION_5/07_tier_full.log) |
| **C2 Inspector Gate** | `python tests/audit_c2_final_inspector.py --verify-docs` | 6 | 6 | 6 | 0 | **PASS** | [`08_audit_c2_inspector.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/PKG5_10B_REVISION_5/08_audit_c2_inspector.log) |

## 2. Invariant & Anti-Fabrication Declarations

1. **Zero Scene Mutation**: No `.blend` files were generated, overwritten, opened, or rendered outside existing test suites. `output/dynamics_playground.blend` remains the unmutated single source of truth for dynamics testing.
2. **Visual Inspection Separation**: Automated pass markers for visual tests (`AUTOMATED_PASS`) indicate headless assertion success; visual acceptance by the user in the Blender GUI remains deferred to established downstream milestones and Task 6H.
3. **No Softened Assertions**: All float tolerances in `tests/` strictly maintain `TOL = 1e-5` (or existing tighter tolerances). Joint limit thresholds in `src/rig/joint_limits.py` remain untouched.
4. **Clean Exit Codes**: Every individual test script and test tier reported return code 0 with zero unexpected output patterns or unhandled exceptions.
