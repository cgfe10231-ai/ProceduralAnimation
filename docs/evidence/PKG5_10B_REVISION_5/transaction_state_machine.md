# Task 10-B-5: Transaction State Machine & Commit Protocol

## 1. Explicit 9-State Lifecycle Machine

`_ArmRigTransactionState` defines a deterministic, non-ambiguous lifecycle state machine for all Arm IK operations:

```mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> SNAPSHOTTING: Snapshot collection, controllers, bones, constraints
    SNAPSHOTTING --> ACTIVE: Snapshot validated and stored
    SNAPSHOTTING --> FAILED: Snapshot read error (propagates, aborts)
    
    state "Phase 1: Reversible Commit Preparation" as P1 {
        ACTIVE --> COMMITTING: All forward mutations executed
    }
    
    state "Phase 2: Logical Commit Confirmation" as P2 {
        COMMITTING --> COMMITTED: Pre-commit invariants passed, depsgraph updated
    }
    
    state "Rollback Path" as RB {
        ACTIVE --> ROLLING_BACK: Exception during mutation
        COMMITTING --> ROLLING_BACK: Exception before Phase 2
        ROLLING_BACK --> ROLLED_BACK: State verified against snapshot
        ROLLING_BACK --> FAILED: Verification failure (dual exception)
    }
    
    state "Phase 3: Irreversible Resource Cleanup" as P3 {
        COMMITTED --> COMMITTED: Irreversible cleanup succeeds
        COMMITTED --> CLEANUP_PENDING: Cleanup error (tracked in tx)
        CLEANUP_PENDING --> COMMITTED: tx.retry_cleanup() converges
    }
    
    ROLLED_BACK --> [*]
    FAILED --> [*]
```

## 2. States Specification

| State | Scope | Description | Rollback Permitted? |
| :--- | :--- | :--- | :--- |
| `CREATED` | Transaction Init | Transaction context instantiated, empty resource tracking lists. | No mutations made |
| `SNAPSHOTTING` | Phase 0 | Deep copy of collection, 4 controllers, 6 bones, constraints. | Aborts cleanly, no rollback needed |
| `ACTIVE` | Mutation Phase | Arm IK business logic executing forward mutations. | Yes (`ROLLING_BACK`) |
| `COMMITTING` | Phase 1 | Reversible commit preparation; depsgraph update and pre-commit hooks. | Yes (`ROLLING_BACK`) |
| `COMMITTED` | Phase 2 | Rig logical mutations confirmed valid and permanent. | **No** (Rig is committed) |
| `ROLLING_BACK` | Rollback Phase | Restoring controllers, bones, constraints, and removing tx collections. | Currently restoring |
| `ROLLED_BACK` | Rollback Exit | State restored and verified matching snapshot (`TOL=1e-5`). | Complete |
| `CLEANUP_PENDING` | Phase 3 Failure | Irreversible cleanup encountered error; uncleaned resources tracked. | No (Retry via `retry_cleanup()`) |
| `FAILED` | Terminal Failure | Verification failed or unrecoverable system crash during rollback. | Terminal error |

## 3. Three-Phase Safe Commit Protocol

1. **Phase 1: Reversible Commit Preparation (`COMMITTING`)**:
   - Ensures all controller transforms and constraint influences are written.
   - Triggers `before_commit_prepare` and `during_commit_prepare` fault injection hooks.
   - Invokes `_depsgraph_update()`.
   - **Guaranteed Invariant**: No stashed objects or doomed datablocks are destroyed in this phase. If any error occurs here, full rollback is executed and verified.
2. **Phase 2: Logical Commit Confirmation (`COMMITTED`)**:
   - Switches transaction state to `_ArmRigTransactionState.COMMITTED`.
   - Triggers `after_logical_commit` fault hook.
   - At this point, the business rig changes are logical truth. The transaction will never revert the active controllers.
3. **Phase 3: Irreversible Resource Cleanup**:
   - Executes only after Phase 2 is committed.
   - Copies doomed stashed items into `tx.uncleaned_stashed_constraints` and `tx.uncleaned_stashed_objects`.
   - Invokes `tx.retry_cleanup()`.
   - If cleanup fails:
     - State becomes `_ArmRigTransactionState.CLEANUP_PENDING`.
     - Error string recorded in `tx.cleanup_error`.
     - Explicit `RuntimeError` raised containing cleanup failure details.
     - Uncleaned resources remain isolated in `tx.uncleaned_stashed_*`.
     - Can be called repeatedly via `tx.retry_cleanup()` until convergence.
