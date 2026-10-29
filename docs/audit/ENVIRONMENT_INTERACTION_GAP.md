# ProceduralAnimation: Environment Interaction Gap Analysis (7A→7B Gate)

> [!NOTE]
> **历史审计快照标识 (Historical Audit Snapshot)**
> * **快照归档基准**：Git SHA `670766a`（Phase 7A 阶段审计归档点，2026-10-27）
> * **历史有效性说明**：本文件为历史阶段性环境交互差距分析报告，**严格保留历史事实记录**。
> * **后续演进与修复现状**：本报告指出的解析环境与网格几何脱节问题在 Environment Gate 01（Unit 1-4）中完成几何网格对齐；双向动力学受力闭环缺口确认为阶段性未接入项，详见 [`docs/audit/environment_gate01_final/PHYSICS_AND_CONTROL_GAPS.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/audit/environment_gate01_final/PHYSICS_AND_CONTROL_GAPS.md)。
> * **最新权威架构文档**：请查阅最新权威文档 [`ARCHITECTURE.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/ARCHITECTURE.md) 与 [`ARCHITECTURE_SYNC.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/ARCHITECTURE_SYNC.md)。

> **Document Status**: COMPLETED ARCHITECTURE AUDIT BASELINE  
> **Target Milestone**: Admission Gate Phase 7A → Phase 7B  
> **Audit Date**: 2026-10-27  
> **Git Reference**: `670766a26fa7b2ba1f8feee609625d01de98cd39`  

---

## 1. Executive Summary: Bidirectional Interaction Gaps

The overarching goal of the ProceduralAnimation project is to achieve continuous, dynamic, physics-grounded character locomotion that seamlessly interacts with arbitrary 3D environments.

This audit evaluates the reality of human-environment interaction as of Phase 7A completion. The central conclusion is that **current interaction is purely unidirectional (feedforward sensory query)**:
* The character queries the environment to read height and slope.
* The character adjusts foot and trunk kinematic targets to match that slope.
* **The character NEVER feels or reacts to physical forces, never senses dynamic slipping, never adjusts balance based on real CoM deviation, and never updates environment geometry.**

---

## 2. Exhaustive Answers to the 10 Environment Interaction Questions

### Q1: Does `EnvironmentQuery` query actual Blender mesh triangles or analytical equations?
* **Actual Disk Reality**: **Analytical equations only.**
* **Technical Evidence**:
  In `src/scene/environment_query.py` (lines 340-420), `DynamicsEnvironmentQuery` defines terrain zones as mathematical geometric objects:
  ```python
  # Analytical plane representation
  self.surfaces = [
      OrientedSurface(name="Ground", z_base=0.0, bounds=(-10.0, 10.0, -10.0, 10.0)),
      OrientedSurface(name="Ramp", z_base=0.0, slope_pitch=0.2618, bounds=(-2.0, 2.0, 4.0, 8.0)),
      ...
  ]
  ```
  When `get_surface_elevation(x, y)` is called, it performs an $O(1)$ analytical 2D point-in-box check and evaluates $Z(x, y) = Z_0 + \tan(\theta) \cdot (y - y_0)$.
* **Implication**: It does **not** perform raycasting against Blender mesh BVH trees. If an artist or procedural script deforms the mesh in Blender, the query remains completely blind to the deformation.

---

### Q2: Is there a Dual Source of Truth between scene building and environment querying?
* **Actual Disk Reality**: **YES. Dual Source of Truth exists.**
* **Technical Evidence**:
  1. `src/scene/builder.py:build_dynamics_playground()` constructs Blender mesh objects with vertices and faces.
  2. `src/scene/environment_query.py:create_standard_dynamics_playground_query()` constructs an independent set of mathematical equations.
* **Current Safeguard**: The dimensions in both files are manually matched to standard values ($L_{ramp}=4.0m$, $\theta=15^\circ$, $Z_{platform}=1.0m$).
* **Requirement for Phase 7B/7C**: Must implement either an automatic analytical-to-mesh exporter or a mesh BVH raycaster (`mathutils.bvhtree.BVHTree.FromMesh`) to establish a single authoritative source of truth.

---

### Q3: Does `ContactModel` feed back into motion planning?
* **Actual Disk Reality**: **NO.**
* **Technical Evidence**:
  `src/motion/contact_model.py` provides `evaluate_limb_contacts_from_armature()` and `enrich_motion_state_with_contacts()`. These functions are invoked *after* `WholeBodyController` has keyframed the frame. The resulting `MultiContactState` (active contacts, contact points, support polygon) is saved into `MotionState.contacts` for telemetry reporting and then dropped. The next frame's `TerrainWalkAction` does not read `MotionState.contacts`.

---

### Q4: Does Whole-Body Center of Mass (CoM) participate in next-frame control?
* **Actual Disk Reality**: **NO.**
* **Technical Evidence**:
  `compute_whole_body_com()` in `src/motion/rigid_link.py` calculates CoM purely as a diagnostic metric. In `TerrainWalkAction.execute_frame()`, pelvic root translation is calculated via a predefined feedforward velocity curve:
  $$y_{root}(t) = y_0 + \int v(t) dt$$
  The actual position of CoM relative to the support foot is **never evaluated to adjust pelvic position, trunk pitch, or step placement**. If the character's CoM leans entirely outside the foot support polygon, the animation continues walking forward unperturbed.

---

### Q5: If IK resolution fails or reaches joint singularity, does it feed back into planning?
* **Actual Disk Reality**: **NO.**
* **Technical Evidence**:
  When `WholeBodyController.execute_frame()` executes, if an IK target is unreachable (beyond maximum leg extension of 0.85m), Blender's internal IK solver stretches the leg to maximum extension and produces residual error. `WholeBodyController` records this in `WholeBodyControlResult.unmet_constraints` (line 172). However:
  * `KinematicBridgeExecutor` does not abort or alter the trajectory.
  * `TerrainWalkAction` is never notified that the foot failed to reach the planned step.
  * The planner blindly proceeds with the next scheduled step.

---

### Q6: Does `ForwardDynamicsState` from Pipeline B affect the 19-bone character pose?
* **Actual Disk Reality**: **NO.**
* **Technical Evidence**:
  `ForwardDynamicsState` (generated by `forward_dynamics.py:integrate_forward_dynamics_single_step()`) contains the simulated rigid body state (position, velocity, quaternion, angular velocity) of a lumped-mass box proxy.
  * In `output/dynamics_playground.blend`, this state drives a floating cube named `DynamicsProxyBox`.
  * `CharacterArmature` has **zero constraints, zero drivers, and zero code links** to `DynamicsProxyBox`.

---

### Q7: What is the exact scope of current environment interaction?
* **Actual Disk Reality**: **Strictly Unidirectional Kinematic Query.**
* **Technical Evidence**:
  The only active link is:
  $$\text{TerrainWalkAction} \xrightarrow{\text{query } Z(x, y), N(x, y)} \text{DynamicsEnvironmentQuery}$$
  The character uses this information strictly to:
  1. Offset root height: $Z_{root} = Z_{terrain} + 0.95m$.
  2. Pitch the trunk forward/backward to align with the slope angle $\theta$.
  3. Clamp the stance foot target height to $Z_{terrain}$.

---

### Q8: How is foot placement adapted to terrain elevation?
* **Actual Disk Reality**:
  * During stance phase, `TerrainWalkAction` sets `FootIK.z` to the exact terrain height $Z_{ground}(x, y)$.
  * During swing phase, it elevates the foot along a sinusoidal clearance curve:
    $$Z_{foot}(t) = (1 - s) \cdot Z_{start} + s \cdot Z_{end} + H_{step} \cdot \sin(\pi s)$$
    where $s \in [0, 1]$ is the normalized phase and $H_{step} = 0.10m$.
  * Foot sole rotation is pitched to match the slope normal $N_{surface}$.

---

### Q9: What is the current status of dynamic obstacle detection and avoidance?
* **Actual Disk Reality**: **UNIMPLEMENTED.**
* **Technical Evidence**:
  `DynamicsEnvironmentQuery` contains spatial corridor check methods (`is_corridor_clear`), but `TerrainWalkAction` does not call them during runtime locomotion. The character will walk straight through any obstacle placed in its path.

---

### Q10: How are foot slipping, slope friction, and reaction torques handled on disk?
* **Actual Disk Reality**: **Kinematic Pinning Only (Zero Friction Simulation).**
* **Technical Evidence**:
  * Foot slipping is prevented by `src/rig/foot_contact.py:lock_foot_contact()`, which locks the `FootIK` empty to fixed Cartesian coordinates in Blender world space.
  * There is **no physical friction cone check** in Pipeline A. Even on an ice surface ($\mu = 0.05$) or a $60^\circ$ incline, the foot remains artificially glued to the spot.
  * Pipeline B simulates friction cones and contact torques on the proxy box, but this is never coupled to the character's feet.

---

## 3. Summary Gap Matrix for Phase 7B Planning

| Capability | Phase 7A Reality | Phase 7B Requirement |
| :--- | :--- | :--- |
| **Terrain Sensing** | Analytical Plane Queries | Unified Query Engine (Mesh Raycasting + Analytical Fallback) |
| **Balance Control** | Open-Loop Feedforward Trajectory | Closed-Loop CoM Feedback (Inverted Pendulum / Capture Point) |
| **Contact Physics** | Kinematic Coordinate Lock | Friction-Constrained Contact Mechanics |
| **IK Fault Handling** | Unnotified Residual Error | Replanning on Reachability / Singularity Alert |
| **Obstacle Awareness**| Hardcoded Waypoint Corridor | Real-time Obstacle Clearance Query |
