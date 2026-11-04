# Task 10-B-5: Resource Ownership & Isolation Contract

## 1. Collection Ownership Model

Previous revisions indiscriminately deleted any collection created between snapshot and rollback. This caused dangerous collateral deletion of external collections created during the transaction.

### Ownership Registration Contract
1. Collections created explicitly by the transaction (e.g. `_ensure_character_collection()` when `Character` did not exist initially) must be registered in the active transaction:
   ```python
   tx.register_created_collection(col, initial_parent=scene.collection)
   ```
2. During rollback, `_rollback_arm_rig_state()` unlinks and removes **only** collections that are in `active_tx.created_collections`.
3. Any collection created by user code or external systems during the active transaction window is strictly protected and remains unlinked and undamaged.
4. If an existing `Character` collection had multiple parents, was renamed, or had children unlinked during the transaction, rollback restores:
   - Its exact original name.
   - All original parent collection linkages.
   - All original child collections and objects.

## 2. Controller & Constraint Replacement Isolation

When `setup_arm_ik()` encounters an invalid object (wrong type, e.g. MESH instead of EMPTY):

1. **Reversible Stashing**:
   - The doomed object is renamed to a private temporary name (e.g. `_stashed_doomed_HandIK.L_...`).
   - The object reference, its datablock, and original collection memberships are stored in `tx.stashed_objects`.
   - The same protocol applies to invalid constraints on bones: stashed into `tx.stashed_constraints`.
2. **Rollback Safety**:
   - If a failure occurs before commit (Phase 1 or earlier), `_rollback_arm_rig_state()` restores the stashed object/constraint:
     - The temporary controller is deleted.
     - The original stashed object is renamed back to its original name.
     - Original parent, matrix_parent_inverse, and collection memberships are restored.
     - Original object pointer (`obj_ptr`) and datablock pointer (`data_ptr`) remain 100% intact.
3. **Commit Cleanup (Phase 3)**:
   - Only after Phase 2 (Logical Commit) succeeds does Phase 3 clean up stashed objects.
   - Exclusive orphaned datablocks (`users == 0`) are removed.
   - Shared datablocks (`users >= 1`) are strictly preserved.
