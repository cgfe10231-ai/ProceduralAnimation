# ProceduralAnimation: Documentation Drift Audit (7A→7B Gate)

> [!NOTE]
> **历史审计快照标识 (Historical Audit Snapshot)**
> * **快照归档基准**：Git SHA `670766a`（Phase 7A 阶段审计归档点，2026-10-27）
> * **历史有效性说明**：本文件为历史阶段性文档漂移分析报告，**严格保留历史事实记录**。
> * **后续演进与同步现状**：本报告指出的文档滞后问题已在 Environment Gate 01 最终架构审计中获得全面同步与收口，参见 [`docs/audit/environment_gate01_final/DOCUMENTATION_SYNC_REPORT.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/audit/environment_gate01_final/DOCUMENTATION_SYNC_REPORT.md)。
> * **最新权威架构文档**：请查阅最新权威文档 [`ARCHITECTURE.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/ARCHITECTURE.md) 与 [`ARCHITECTURE_SYNC.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/ARCHITECTURE_SYNC.md)。

> **Document Status**: COMPLETED ARCHITECTURE AUDIT BASELINE  
> **Target Milestone**: Admission Gate Phase 7A → Phase 7B  
> **Audit Date**: 2026-10-27  
> **Git Reference**: `670766a26fa7b2ba1f8feee609625d01de98cd39`  

---

## 1. Executive Summary of Documentation Drift

A systematic comparison between the existing architectural documentation and the disk codebase was conducted. The audit reveals **significant architectural drift**:

1. **Stale Blueprint Snapshots**:
   * `ARCHITECTURE.md` is frozen at **v2.3 (Task 6G-C-R3B-2 snapshot)**. It describes historical states where actions allegedly bypassed WBC, completely missing Phase 6G-D dynamics and Phase 7A terrain traversal.
   * `ARCHITECTURE_SYNC.md` is frozen at **v3.0 (Task 6G-D-C2-FINAL snapshot)**. It documents the centroidal dynamics freeze, but does not document Phase 7A character-in-playground integration or terrain traversal.
2. **Missing Phase 7A Production Modules**:
   * `src/motion/terrain_walk.py` (477 lines, containing `TerrainWalkAction`, `TerrainRouteInput`, `TerrainTraversalSpec`, `plan_terrain_footsteps`) is completely absent from `ARCHITECTURE.md` and `ARCHITECTURE_SYNC.md`.
   * Phase 7 scene modules (`playground_terrain_traversal.py`, `playground_character_assembly.py`, `playground_character_integration.py`, `playground_terrain_validation.py`) are unmapped in primary architecture diagrams.
3. **Symbol & Terminology Mismatches**:
   * Architecture texts repeatedly refer to `JointModel` as a class; the actual production class in `src/motion/joint_limits.py:152` is `HumanoidROMModel`.
   * Architecture diagrams refer to `KinematicBridge`; the actual production executor in `src/motion/kinematic_bridge.py:173` is `KinematicBridgeExecutor`.
   * Architecture texts refer to `FootContactAdapter` as an adapter object; `src/rig/foot_contact.py` actually provides standalone functional primitives (`lock_foot_contact`, `unlock_foot_contact`, `evaluate_foot_support`).

---

## 2. Granular Document Drift Matrix

| Document | Stated Version & Scope | Actual Disk Code Reality | Drift Level | Required Remediation |
| :--- | :--- | :--- | :--- | :--- |
| `ARCHITECTURE.md` | v2.3 (Task 6G-C-R3B-2) | Codebase is at Phase 7A-2. Actions no longer bypass WBC. Numerical dynamics kernel (6G-D) is implemented. Phase 7A terrain locomotion is deployed. | **HIGH (Stale by 2 Phases)** | Update `ARCHITECTURE.md` to v3.1 / Phase 7 baseline after audit review. |
| `ARCHITECTURE_SYNC.md` | v3.0 (Task 6G-D-C2) | Codebase has completed Task 7A-1 and Task 7A-2. Character is assembled in `dynamics_playground`. `TerrainWalkAction` is active. | **MEDIUM (Stale by 1 Phase)** | Synchronize Phase 7A module references and entry points into dependency map. |
| `docs/ROADMAP_FOUNDATION_TO_FULLBODY.md` | Pre-Phase 7 roadmap | Accurately predicted Phase 7A, but lists Phase 7B/7C items that need realignment based on audit discoveries. | **LOW (Accurate as roadmap)** | Keep as historical reference; update Phase 7B entrance gate conditions. |
| `docs/FOUNDATION_STATE_OWNERSHIP.md` | Task 6G-D baseline | Accurately documents exclusive writer principles, but omits `TerrainWalkAction` state transitions. | **LOW** | Add `TerrainWalkAction` to ownership catalog. |
| `docs/ARCHITECTURE_CHANGE_GATE.md` | Task 6G-D-FINAL SSOT | Authoritative and strictly enforced. All 10 anti-drift rules remain 100% valid. | **ZERO DRIFT** | Retain as permanent constitutional standard. |

---

## 3. Discrepancy Case Studies

### Case Study 1: Stale Bypass Statements in `ARCHITECTURE.md`
* **Text in `ARCHITECTURE.md:57`**:
  > *"管线一（历史动作管线）：StartStopWalkAction, RunAction... 完全绕过 WholeBodyController, JointModel 与 ContactModel。"*
* **Actual Disk Reality**:
  In `src/motion/framework.py:442-530`, `StartStopWalkAction` was refactored in Task 6G-C-R3B to route all poses through `KinematicBridgeExecutor` and `WholeBodyController`. There is **zero direct bone manipulation** in the active pipeline.
* **Impact**: Creates false impression that the codebase is still riddled with legacy bypasses.

### Case Study 2: Phantom Class Name `JointModel`
* **Text in `ARCHITECTURE.md:16` and `ARCHITECTURE_SYNC.md:18`**:
  > *"JointModel 负责 ROM 检查，严禁截断后虚报成功..."*
* **Actual Disk Reality**:
  The module `src/motion/joint_limits.py` defines `HumanoidROMModel` (dataclass) and `enforce_joint_limits` (function). A class named `JointModel` does not exist on disk.
* **Impact**: Causes confusion when developers or automated tools search for class `JointModel`.

### Case Study 3: Omission of `TerrainWalkAction`
* **Text in `ARCHITECTURE_SYNC.md:38-42`**:
  Lists only `StartStopWalkAction`, `RunAction`, `SprintStartAction`, `SprintBrakeAction`.
* **Actual Disk Reality**:
  `src/motion/terrain_walk.py` is the **core locomotion engine of Phase 7A**, handling continuous terrain traversal across flat, ramp, and platform surfaces for 280 frames.
* **Impact**: Anyone relying on `ARCHITECTURE_SYNC.md` would not know how terrain traversal works.

---

## 4. Remediation Recommendations for Phase 7B Entry

1. **Document Freeze & Transition**:
   * Maintain `docs/ARCHITECTURE_CHANGE_GATE.md` as the immutable gatekeeper.
   * Consolidate the 8 audit reports in `docs/audit/` as the single authoritative architecture snapshot for the 7A $\to$ 7B boundary.
2. **Planned Architectural Synchronizations**:
   * Prior to writing any production code for Phase 7B-1, update `ARCHITECTURE.md` to v3.1 to incorporate Phase 7A reality (`TerrainWalkAction`, `DynamicsEnvironmentQuery` integration, and `DynamicsPlayground` scene structure).
