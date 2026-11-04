# Task 10-B-5: Fault Injection & Boundary Matrix

## 1. Test Fault Injection Architecture

All fault injection hooks in `src/rig/arm_ik.py` are strictly private, accessible solely via private test fixtures `_set_test_fault_injection_hook()` and `_clear_test_fault_injection_hook()`. They never leak across tests or exceptions.

Additionally, dependency graph updates are isolated behind an explicit adapter boundary: `_DEPSGRAPH_UPDATER`, configurable for deterministic unit testing via `_set_test_depsgraph_updater()` and `_clear_test_depsgraph_updater()`.

## 2. Injected Fault Points & System Behaviors

| Hook Stage | Location in Code | Subsystem Under Test | Injected Failure | Verified Behavior | Relevant Tests |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `during_snapshot_creation` | `_snapshot_arm_rig_state()` | Snapshot Phase | Snapshot generation abort | Aborts cleanly, leaves transaction stack depth 0, no scene pollution | TEST-58, TEST-74 |
| `setup_arm_ik_after_first_controller` | `setup_arm_ik()` | Controller Instantiation | Write abort after first controller | Rolls back created controller, restores original collection hierarchy | TEST-39, TEST-72, TEST-74 |
| `setup_arm_ik_after_controller_replaced` | `setup_arm_ik()` | Controller Replacement | Write abort after stashing wrong object | Restores stashed original object, preserves object pointer & datablock | TEST-40 |
| `setup_arm_ik_after_constraints_or_prebend` | `setup_arm_ik()` | Constraint Configuration | Write abort after adding constraints | Rolls back newly added constraints, restores original bone constraints | TEST-41, TEST-73 |
| `set_hand_ik_target_during_auto_init` | `set_hand_ik_target()` | Auto-initialization | Abort during auto-init invocation | Reverts entire scene to uninitialized state | TEST-42 |
| `set_hand_ik_target_after_hand_location` | `set_hand_ik_target()` | Target Positioning | Abort after setting HandIK location | Reverts location write, protects concurrent external collections | TEST-43, TEST-62, TEST-70, TEST-71, TEST-75 |
| `set_hand_ik_target_after_hand_rotation` | `set_hand_ik_target()` | Target Rotation | Abort after setting HandIK rotation | Reverts rotation write to snapshot | TEST-44 |
| `set_hand_ik_target_after_pole_location` | `set_hand_ik_target()` | Pole Positioning | Abort after setting ElbowPole location | Reverts pole location write to snapshot | TEST-45 |
| `set_hand_ik_target_between_influences` | `set_hand_ik_target()` | Constraint Sync | Abort between ArmIK and HandRot writes | Keeps constraint influences strictly in sync | TEST-46 |
| `set_hand_ik_target_after_rot_influence` | `set_hand_ik_target()` | Hand Rotation Influence | Abort after setting HandRot influence | Reverts all written influences | TEST-47 |
| `set_hand_ik_target_during_state_read` | `set_hand_ik_target()` | State Readback | Abort during return state calculation | Revokes all forward mutations | TEST-48 |
| `set_hand_ik_target_during_depsgraph_update` | `set_hand_ik_target()` | Depsgraph Pre-hook | Simulated exception before update call | Reverts all writes, restores snapshot | TEST-61 |
| `_DEPSGRAPH_UPDATER` Call Boundary | `_depsgraph_update()` | Depsgraph Adapter Boundary | Call boundary exception during update | Propagates exception, triggers complete atomic rollback, stack=0 | TEST-68 |
| `before_commit_prepare` | `_arm_rig_transaction()` | Phase 1 Commit Preparation | Early pre-commit hook failure | Rolls back, preserves stashed resources, stack depth 0 | TEST-65 |
| `during_commit_prepare` | `_arm_rig_transaction()` | Phase 1 Commit Preparation | Late pre-commit hook failure | Full rollback to snapshot, verifier passes | TEST-65 |
| `after_logical_commit` | `_arm_rig_transaction()` | Phase 2 Logical Commit | Failure after logical commit confirmed | State remains COMMITTED, rig writes retained | TEST-66 |
| `during_commit_cleanup` | `_arm_rig_transaction()` | Phase 3 Resource Cleanup | Failure during irreversible cleanup | State becomes CLEANUP_PENDING, tracks uncleaned resources, retries via `retry_cleanup()` | TEST-64, TEST-66, TEST-67 |
| `during_constraint_property_restore` | `_rollback_arm_rig_state()` | Rollback Restoration | Exception writing RNA property | Aggregates dual exceptions (primary + restoration), reports bone/con/prop context | TEST-70 |
| `during_rollback_verification` | `_arm_rig_transaction()` | Rollback Verification | Exception during state verification | Reports primary error + rollback verification failure, state=FAILED | TEST-52 |
