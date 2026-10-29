# ProceduralAnimation: Actual Runtime Architecture Audit (7A→7B Gate)

> [!NOTE]
> **历史审计快照标识 (Historical Audit Snapshot)**
> * **快照归档基准**：Git SHA `670766a`（Phase 7A 阶段审计归档点，2026-10-27）
> * **历史有效性说明**：本文件为历史阶段性运行时架构分析产物，**严格保留历史事实记录**。
> * **后续演进与修复现状**：自本报告归档后，工程实施了 Environment Gate 01，彻底消除了解析环境与网格环境的双重事实源，确立了 `BlenderMeshEnvironmentAdapter` 为单一网格几何感知来源。最新全量架构事实请查阅 [`docs/audit/environment_gate01_final/`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/audit/environment_gate01_final/)。
> * **最新权威架构文档**：请查阅最新权威文档 [`ARCHITECTURE.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/ARCHITECTURE.md) 与 [`ARCHITECTURE_SYNC.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/ARCHITECTURE_SYNC.md)。

> **Document Status**: COMPLETED ARCHITECTURE AUDIT BASELINE  
> **Target Milestone**: Admission Gate Phase 7A → Phase 7B  
> **Audit Date**: 2026-10-27  
> **Git Reference**: `670766a26fa7b2ba1f8feee609625d01de98cd39`  

---

## 1. Architectural Overview: The Dual-Pipeline Reality

An exhaustive static and dynamic call-chain audit of the ProceduralAnimation codebase reveals a fundamental architectural bifurcation: **the system consists of two completely independent pipelines that run in parallel but do not feed back into one another**.

```
+----------------------------------------------------------------------------------------------------+
|                                      DUAL PIPELINE REALITY ON DISK                                 |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  [ PIPELINE A: 19-Bone Humanoid Kinematic Animation Pipeline ]                                     |
|                                                                                                    |
|     +-------------------------+                                                                    |
|     | DynamicsEnvironmentQuery|                                                                    |
|     +------------+------------+                                                                    |
|                  | (Analytical Z & Normals Query)                                                  |
|                  v                                                                                 |
|     +------------+------------+                                                                    |
|     | TerrainWalkAction       |                                                                    |
|     | (or StartStopWalkAction)|                                                                    |
|     +------------+------------+                                                                    |
|                  | (KinematicPlannedPose)                                                          |
|                  v                                                                                 |
|     +------------+------------+                                                                    |
|     | KinematicBridgeExecutor |                                                                    |
|     +------------+------------+                                                                    |
|                  | (WholeBodyControlTargets)                                                       |
|                  v                                                                                 |
|     +------------+------------+                                                                    |
|     | WholeBodyController     |                                                                    |
|     +------------+------------+                                                                    |
|                  | (PoseBone Rotations & IK Empty Locations)                                       |
|                  v                                                                                 |
|     +------------+------------+      (Post-Pose Read-Only)      +-----------------------------+    |
|     | CharacterArmature       | =============================> | Physical Telemetry Engine   |    |
|     | (19 Bones + 4 IK Empties|                                | (rigid_link, body_kinematics|    |
|     +-------------------------+                                |  body_inertia, contact_model|    |
|                                                                 +--------------+--------------+    |
|                                                                                |                   |
|                                                                                v                   |
|                                                                 [ MotionState Diagnostic Bag ]     |
|                                                                 (DEAD END - NO FEEDBACK TO PHASE 2)|
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  [ PIPELINE B: 6-DOF Centroidal Numerical Dynamics Simulation Pipeline ]                           |
|                                                                                                    |
|     +-------------------------+                                                                    |
|     | DesiredMotionReference  |                                                                    |
|     +------------+------------+                                                                    |
|                  | (Desired CoM Trajectory & Orientation)                                          |
|                  v                                                                                 |
|     +------------+------------+                                                                    |
|     | ClosedLoopDynamics-     |                                                                    |
|     | Coordinator             |                                                                    |
|     +------------+------------+                                                                    |
|                  | (Commanded Centroidal Wrench)                                                   |
|                  v                                                                                 |
|     +------------+------------+                                                                    |
|     | ContactForceSolver (QP) |                                                                    |
|     +------------+------------+                                                                    |
|                  | (Ground Reaction Forces per contact point)                                      |
|                  v                                                                                 |
|     +------------+------------+                                                                    |
|     | forward_dynamics        |                                                                    |
|     | (Symplectic Euler / RK4)|                                                                    |
|     +------------+------------+                                                                    |
|                  | (ForwardDynamicsState: CoM pos, vel, quat, omega)                               |
|                  v                                                                                 |
|     +------------+------------+                                                                    |
|     | dynamics_visualizer     |                                                                    |
|     +------------+------------+                                                                    |
|                  | (Spawns floating proxy cube & force arrow meshes)                               |
|                  v                                                                                 |
|     [ output/dynamics_playground.blend Floating Telemetry Arrows ]                                 |
|     (DOES NOT DRIVE, INTERACT WITH, OR KNOW ABOUT THE 19-BONE HUMANOID RIG)                         |
+----------------------------------------------------------------------------------------------------+
```

### Critical Finding on Pipeline Decoupling
1. **Pipeline A (Humanoid Locomotion)** produces continuous, anatomically constrained 19-bone character motion. It queries the terrain analytically via `DynamicsEnvironmentQuery`, plans foot placement and root trajectory, routes through `KinematicBridgeExecutor` and `WholeBodyController`, clamps joint ROM via `joint_limits.py`, and writes keyframes to `CharacterArmature`.
2. **Pipeline B (Centroidal Numerical Dynamics)** is a self-contained, mathematically rigorous 6-DOF centroidal rigid body simulator (`forward_dynamics.py`, `contact_force_solver.py`, `closed_loop_dynamics.py`). It simulates a single lumped-mass rigid box subject to GRFs and friction cones.
3. **Zero Closed-Loop Coupling**: Pipeline B does **not** drive the 19-bone humanoid. Conversely, the whole-body CoM and inertia calculated by Pipeline A's telemetry modules (`rigid_link.py`, `body_inertia.py`) are **never fed into Pipeline B's coordinator** to correct character balance or compute dynamic recovery steps. The telemetry extracted from `CharacterArmature` is purely written into `MotionState` diagnostic fields and immediately discarded at the end of each frame.

---

## 2. Reconstructed Production Execution Chains (Chains A through F)

### Chain A: Character & Rig Initialization Chain
* **Purpose**: Instantiates the 13 visual placeholder body meshes, builds the 19-bone armature, establishes parent hierarchies, and configures IK/pole constraints.
* **Call Sequence**:
  1. `src/scene/playground_character_assembly.py` $\to$ calls `src/character/builder.py:build_character()`:
     * Spawns 13 cube/sphere meshes under `CharacterRoot`.
     * Calculates `world_min_z` to align soles at $Z = 0.0m$.
  2. `src/scene/playground_character_assembly.py` $\to$ calls `src/rig/builder.py:build_rig()`:
     * Creates `CharacterArmature` edit bones following `BONE_HIERARCHY` and `BONE_SPECIFICATIONS`.
  3. `src/scene/playground_character_assembly.py` $\to$ calls `src/rig/builder.py:bind_character_to_rig()`:
     * Parents the 13 meshes to their respective bones (`BONE` parent type).
  4. `src/scene/playground_character_assembly.py` $\to$ calls `src/rig/ik.py:setup_leg_ik()`:
     * Adds `IK` constraint to `Shin.L` and `Shin.R` (`chain_count = 2`).
     * Creates `FootIK.L`, `FootIK.R`, `KneePole.L`, `KneePole.R` Empty objects.
  5. `src/scene/playground_character_assembly.py` $\to$ calls `src/rig/arm_ik.py:setup_arm_ik()`:
     * Adds `IK` constraint to `Forearm.L` and `Forearm.R` (`chain_count = 2`).
     * Creates `HandIK.L`, `HandIK.R`, `ElbowPole.L`, `ElbowPole.R` Empty objects.
* **Status**: `REAL PRODUCTION CALL` (Verified 100% active on disk).

### Chain B: Kinematic Locomotion Execution Chain
* **Purpose**: Generates continuous per-frame kinematic poses, converts them to Cartesian end-effector targets, and executes whole-body pose resolution.
* **Call Sequence**:
  1. Entry Point: `run_task7a2_terrain_traversal.py` or `src/scene/playground_character_assembly.py`.
  2. Orchestrator: `MotionPlanner.execute(context, initial_state)` (`src/motion/framework.py`).
  3. Action Planner: `TerrainWalkAction.execute_frame(frame, context, state)` (`src/motion/terrain_walk.py`):
     * Evaluates root forward displacement and ground clearance.
     * Generates left and right foot swing/stance curves via sine/parabolic interpolation.
     * Computes trunk pitch adaptation: $\theta = \text{pitch\_from\_surface\_normal}(N_{\text{surface}})$.
     * Packages output into `KinematicPlannedPose`.
  4. Gateway Conduit: `KinematicBridgeExecutor.execute_frame(frame, planned_pose, state)` (`src/motion/kinematic_bridge.py`):
     * Validates target finite numbers.
     * Packages data into `WholeBodyControlTargets`.
     * Calls `WholeBodyController.execute_frame()`.
  5. Authoritative Solver: `WholeBodyController.execute_frame(frame, targets, ...)` (`src/motion/whole_body_controller.py`):
     * Applies trunk posture to `Root`, `Hips`, `Spine`, `Chest`, `Neck`, `Head`.
     * Clamps joint angles via `src/motion/joint_limits.py:enforce_joint_limits()`.
     * Positions IK targets: `FootIK.L`, `FootIK.R`, `HandIK.L`, `HandIK.R`.
     * Inserts keyframes into the active Blender Action.
* **Status**: `REAL PRODUCTION CALL` (Verified 100% active on disk).

### Chain C: Contact Enforcement Chain
* **Purpose**: Enforces kinematic locking of the support foot during stance phase and releases it during swing.
* **Call Sequence**:
  1. `TerrainWalkAction` specifies contact intent (`is_left_support`, `is_right_support`) in `KinematicPlannedPose`.
  2. `KinematicBridgeExecutor` passes contact flags to `WholeBodyControlTargets`.
  3. `WholeBodyController` calls `src/rig/foot_contact.py:lock_foot_contact()` or `unlock_foot_contact()`:
     * When locked, clamps `FootIK` target location to world stance anchor and inserts keyframe.
     * When unlocked, positions `FootIK` along the planned swing trajectory.
* **Status**: `REAL PRODUCTION CALL` (Verified 100% active on disk).

### Chain D: Physical Telemetry Extraction Chain (Post-Pose Read-Only)
* **Purpose**: Extracts physical metrics from the solved character pose for validation and diagnostics.
* **Call Sequence**:
  1. `src/motion/rigid_link.py:compute_whole_body_com(armature_obj)`:
     * Reads current pose bone positions.
     * Calculates 15-segment CoM and total whole-body CoM ($M = 70.0 kg$).
  2. `src/motion/body_kinematics.py:enrich_motion_state_with_kinematics(state, snapshot)`:
     * Computes linear and angular velocities via finite differences.
  3. `src/motion/body_inertia.py:compute_whole_body_inertia(...)`:
     * Calculates whole-body $3\times 3$ inertia tensor about CoM via Steiner's theorem.
  4. `src/motion/contact_model.py:enrich_motion_state_with_contacts(...)`:
     * Computes 2D support polygon convex hull from foot contact records.
* **Status**: `IMPLEMENTED_READ_ONLY` (Executed during validation and frame enrichment; results are strictly diagnostic and **never feed back into Chain B**).

### Chain E: Numerical Centroidal Dynamics Chain (Pipeline B)
* **Purpose**: Simulates 6-DOF centroidal physics and GRFs on a lumped-mass box proxy.
* **Call Sequence**:
  1. Entry Point: `run_dynamics_playground.py`.
  2. Coordinator: `ClosedLoopDynamicsCoordinator.step_closed_loop_dynamics()` (`src/motion/closed_loop_dynamics.py`):
     * Evaluates tracking error against `DesiredMotionReference`.
     * Computes commanded force and torque wrench via PD feedback.
  3. Force Solver: `solve_contact_forces()` (`src/motion/contact_force_solver.py`):
     * Formulates Quadratic Program with Coulomb friction cone constraints.
     * Solves optimal ground reaction forces ($f_1, f_2, \dots$) via SPG / SLSQP.
  4. Integrator: `integrate_forward_dynamics_single_step()` (`src/motion/forward_dynamics.py`):
     * Integrates Newton-Euler equations via Symplectic Euler or RK4.
     * Produces new `ForwardDynamicsState` (position, velocity, quaternion, angular velocity).
  5. Telemetry Visualizer: `inject_dynamics_visualization()` (`src/scene/dynamics_visualizer.py`):
     * Moves a floating cube and draws force arrows in `output/dynamics_playground.blend`.
* **Status**: `IMPLEMENTED_STANDALONE` (Completely decoupled from the 19-bone character).

### Chain F: Scene & Environment Query Chain
* **Purpose**: Provides spatial terrain geometry to the locomotion planner.
* **Call Sequence**:
  1. `DynamicsEnvironmentQuery` initialized via `create_standard_dynamics_playground_query()` (`src/scene/environment_query.py`).
  2. `TerrainWalkAction` queries elevation and surface slope:
     * `elev = query.get_surface_elevation(x, y)`
     * `normal = query.get_surface_normal(x, y)`
  3. Planner adapts stride height, foot roll, and trunk lean based on returned query values.
* **Status**: `REAL PRODUCTION CALL` (Pure analytical query; no BVH raycasting against Blender mesh geometry).

---

## 3. The Canonical 6-Phase Per-Frame Protocol vs. Actual Implementation

The project specification mandates a strict 6-phase per-frame execution protocol. The table below details what is actually executed on disk in Phase 7A:

| Phase | Specification Role | Actual Disk Implementation | Calling Module | Code Status |
| :--- | :--- | :--- | :--- | :--- |
| **Phase 1** | Environment & Surface Sensing | Samples analytical elevation $Z(x, y)$ and slope normal $N$ from mathematical planes | `src/scene/environment_query.py` | `ACTIVE` (Analytical only; no mesh raycast) |
| **Phase 2** | Kinematic Planning & Target Generation | Computes root progression, swing curves, trunk pitch; packages into `KinematicPlannedPose` | `src/motion/terrain_walk.py` | `ACTIVE` (Kinematic only; no CoM balance loop) |
| **Phase 3** | Inverse Kinematics & Whole-Body Resolution | Hands off to Bridge $\to$ WBC applies bone rotations, positions IK empties, clamps ROM | `src/motion/kinematic_bridge.py` & `src/motion/whole_body_controller.py` | `ACTIVE` (Enforces anatomical limits & IK) |
| **Phase 4** | Physical Contact Enforcement | Locks stance foot empty location to ground anchor; unlocks swing foot | `src/rig/foot_contact.py` | `ACTIVE` (Kinematic clamping; no force simulation) |
| **Phase 5** | Physical Telemetry Extraction | Computes Whole-Body CoM, segment inertia, and velocity snapshots | `src/motion/rigid_link.py` & `src/motion/body_inertia.py` | `READ_ONLY` (Logged to `MotionState`; no feedback) |
| **Phase 6** | Keyframing & Verification | Inserts F-Curve keyframes on bones and empties; logs frame diagnostics | `src/motion/whole_body_controller.py` | `ACTIVE` (Inserts keyframes; records metrics) |

---

## 4. Architectural Gaps for Phase 7B Admission

Before entering Phase 7B (Full-Body Dynamic Balance & Terrain Adaptation), the following architectural realities must be recognized:

1. **Missing Feedback Arc (Phase 5 $\to$ Phase 2)**:
   In the current codebase, Whole-Body CoM is calculated in Phase 5 *after* the pose has already been committed and keyframed. If the character's CoM drifts outside the support polygon, there is zero recovery mechanism. Phase 7B will require feeding CoM error back into Phase 2 to adjust foot placement or trunk lean in real time.
2. **Decoupled Solvers (Pipeline A vs Pipeline B)**:
   The advanced QP contact force solver (`contact_force_solver.py`) and numerical forward integrator (`forward_dynamics.py`) are fully functional but completely isolated. They operate on a rigid box proxy and have never been connected to the 19-bone character's inertia or contact points.
3. **Analytical Environment Disconnect**:
   `DynamicsEnvironmentQuery` evaluates mathematical formulas rather than Blender scene mesh geometry. If terrain meshes are deformed in the viewport, the character will not adapt unless the analytical database is manually synchronized.
