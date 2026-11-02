# PKG-5 / 09-B-4 Test Execution Evidence Archive

> **Evidence Baseline Commit**: `0b42cb1d7dc685d1be7210bc1280519658f85809`
>
> **Generation Date**: 2026-11-02
>
> **Environment**: Windows 11 / Blender 5.1.1 / Python 3.11.9
>
> **09-B Acceptance Status**: `ACCEPTED — VERIFIED`

---

## 1. Evidence Directory

| Directory | Test Scope | Planned | Executed | Result |
|---|---|---:|---:|---|
| [01_world_rotation](01_world_rotation/) | 09-B World Rotation | 1 suite / 27 inner tests | 1 | PASS |
| [02_ground_height](02_ground_height/) | 09-A Ground Height | 1 suite / 20 inner tests | 1 | PASS |
| [03_worldspace_init_reset](03_worldspace_init_reset/) | 08 Worldspace Init/Reset | 1 suite / 6 inner tests | 1 | PASS |
| [04_tier_quick](04_tier_quick/) | Quick Tier | 19 suites | 19 | PASS |
| [05_tier_physics](05_tier_physics/) | Physics Tier | 25 suites | 25 | PASS |
| [06_tier_motion](06_tier_motion/) | Motion Tier | 12 suites | 12 | PASS |
| [07_tier_full](07_tier_full/) | Full Tier | 40 suites | 40 | PASS |
| [08_verify_docs](08_verify_docs/) | C2 Final Inspector | 6 self-tests + documentation audit | 1 | PASS |

Each test directory contains its own JSON report, Markdown report and console output. The first three targeted suites also include their inner test runner console output.

## 2. Targeted Test Results

| Test Suite | Inner Tests | Result | Exit Code |
|---|---:|---|---:|
| `leg_ik_world_rotation_contract` | 27/27 | PASS | 0 |
| `leg_ik_ground_height_contract` | 20/20 | PASS | 0 |
| `leg_ik_worldspace_init_reset` | 6/6 | PASS | 0 |

The 09-B World Rotation test output explicitly records:

`Ran 27 tests`

`OK`

## 3. Tiered Regression Results

| Tier | Planned | Executed | Ordinary PASS | AUTOMATED_PASS | FAIL | SKIPPED | NOT_RUN | Exit Code |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Quick | 19 | 19 | 16 | 3 | 0 | 0 | 0 | 0 |
| Physics | 25 | 25 | 22 | 3 | 0 | 0 | 0 | 0 |
| Motion | 12 | 12 | 6 | 6 | 0 | 0 | 0 | 0 |
| Full | 40 | 40 | 31 | 9 | 0 | 0 | 0 | 0 |

All four tier runners exited with code 0.

**AUTOMATED_PASS is not equivalent to visual acceptance.** The 9 Full Tier entries marked AUTOMATED_PASS still require the corresponding visual inspection. They are not represented as visually accepted by this archive.

This visual-review distinction does not alter the 09-B targeted suite result, where all 27 tests returned ordinary PASS.

## 4. Documentation Integrity Check

`tests/audit_c2_final_inspector.py --verify-docs`

Result:

- Validator self-tests: 6/6 PASS.
- Referenced source and test paths: PASS.
- Phantom symbol references: 0.
- Process exit code: 0.

## 5. Acceptance Evidence

The 09-B-4 acceptance is supported by:

- Production repair commit: `52d66dfd529627a9fbc8bae6ffcf6f4fee6c64d8`.
- TEST-24 assertion extension: `3881aaadd58f76ffce18faf5d9e880bc49b82f97`.
- This evidence archive commit: `0b42cb1d7dc685d1be7210bc1280519658f85809`.

09-B-4 is accepted and verified. The next PKG-5 node is Task 10 / Upper-Limb IK/FK.
