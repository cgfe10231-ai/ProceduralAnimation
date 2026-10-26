# ProceduralAnimation: State Ownership & Mutation Matrix (7A→7B Gate)

> **Document Status**: COMPLETED ARCHITECTURE AUDIT BASELINE  
> **Target Milestone**: Admission Gate Phase 7A → Phase 7B  
> **Audit Date**: 2026-10-27  
> **Git Reference**: `670766a26fa7b2ba1f8feee609625d01de98cd39`  

---

## 1. Executive Summary of State Ownership

To prevent competing writes, race conditions, and animation jitter, the ProceduralAnimation architecture establishes a strict **Single Source of Truth (SSOT)** and **Exclusive Writer Rule** across all character assets and data structures.

This audit inspects every data object, pose bone, Empty controller, and dataclass across the codebase to verify:
1. Which module has exclusive write permission.
2. Which modules have read-only access.
3. Every physical site in code where `.location`, `.rotation_euler`, `.matrix_world`, or `.keyframe_insert` is called.
4. Identification of any potential competing writes or out-of-order mutations.

---

## 2. Asset & Data Structure Ownership Matrix

| Target Object / Data Structure | Exclusive Writer (SSOT) | Authorized Readers | Prohibited Writers | Mutation Method | Concurrency / Conflict Risk |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`CharacterRoot`** | `src/character/builder.py` (init) / `WholeBodyController` (runtime) | All scene, camera, validation modules | Actions, Planners, KinematicBridge | `.location`, `.rotation_euler`, `.keyframe_insert()` | **NONE (Single Writer)** |
| **`CharacterArmature` (Object)** | `src/rig/builder.py` (creation) | All modules | Runtime planners | `bpy.data.armatures.new()` | **NONE (Static after setup)** |
| **Trunk Pose Bones (`Root`, `Hips`, `Spine`, `Chest`, `Neck`, `Head`)** | `WholeBodyController` (`src/motion/whole_body_controller.py`) | `rigid_link.py`, `body_kinematics.py`, `body_inertia.py`, validation | `MotionPlanner`, Actions, `KinematicBridgeExecutor` | `.rotation_euler = ...`, `.keyframe_insert("rotation_euler")` | **NONE (WBC exclusive writer)** |
| **Arm Pose Bones (`Clavicle`, `UpperArm`, `Forearm`, `Hand`)** | `WholeBodyController` (`src/motion/whole_body_controller.py`) | `rigid_link.py`, `body_kinematics.py`, `body_inertia.py` | `MotionAction`, `KinematicBridgeExecutor` | Driven by Blender `IK` constraint or FK rotation | **NONE (WBC sets target/FK)** |
| **Leg Pose Bones (`Thigh`, `Shin`, `Foot`)** | Blender IK Constraint (driven by `FootIK`) | `rigid_link.py`, `body_kinematics.py`, `body_inertia.py` | Direct bone writers | Blender internal constraint evaluation | **NONE (Constrained to FootIK)** |
| **`FootIK.L` & `FootIK.R` (Empties)** | `WholeBodyController` via `src/rig/foot_contact.py` | `rigid_link.py`, `contact_model.py`, validation | `MotionPlanner`, raw scripts | `.location = ...`, `.keyframe_insert("location")` | **LOW (Managed via WBC contact phase)** |
| **`HandIK.L` & `HandIK.R` (Empties)** | `WholeBodyController` via `src/rig/arm_ik.py` | Validation scripts | Direct scripts | `.location = ...`, `.keyframe_insert("location")` | **NONE (WBC exclusive writer)** |
| **`KneePole.L/R`, `ElbowPole.L/R`** | `src/rig/ik.py`, `src/rig/arm_ik.py` (setup & update) | Blender IK solver | Actions, Planners | `.location = ...` | **NONE (Pole vectors updated by WBC)** |
| **`MotionState` (Dataclass)** | `src/motion/framework.py` & `src/motion/terrain_walk.py` | `KinematicBridgeExecutor`, WBC, Telemetry | Standalone physics solvers | State copy with updated fields (`replace`) | **NONE (Functional progression)** |
| **`KinematicPlannedPose` (Dataclass)** | `MotionAction` (`TerrainWalkAction`) | `KinematicBridgeExecutor` | WBC, Rig modules | Instantiated per-frame by Action | **NONE (Immutable input to Bridge)** |
| **`WholeBodyControlTargets` (Dataclass)**| `KinematicBridgeExecutor` | `WholeBodyController` | Actions, Pose bones | Instantiated per-frame by Bridge | **NONE (Immutable input to WBC)** |
| **`WholeBodyControlResult` (Dataclass)** | `WholeBodyController` | `KinematicBridgeExecutor`, validation | Telemetry extractors | Instantiated at end of frame by WBC | **NONE (Return value)** |
| **`ForwardDynamicsState` (Dataclass)** | `src/motion/forward_dynamics.py` | `ClosedLoopDynamicsCoordinator` | Pipeline A humanoid modules | Integrated per sub-step in Pipeline B | **NONE (Pipeline B exclusive)** |
| **Whole-Body CoM (`compute_whole_body_com`)** | `src/motion/rigid_link.py` (read-only extractor) | `MotionState.telemetry`, validation | No one mutates CoM directly | Read-only calculation from pose | **NONE (Pure observation)** |
| **Whole-Body Inertia Tensor** | `src/motion/body_inertia.py` (read-only extractor) | `MotionState.telemetry`, validation | No one mutates inertia directly | Read-only calculation from pose | **NONE (Pure observation)** |

---

## 3. Comprehensive Code Mutation Sites Audit

The table below lists all disk locations where Blender scene objects, pose bones, and animation channels are physically modified in the production pipeline:

### 3.1 Pose Bone Rotations & Translations
* **`src/motion/whole_body_controller.py:357-368`**:
  ```python
  bone = armature_obj.pose.bones[bone_name]
  bone.rotation_mode = "XYZ"
  bone.rotation_euler = Euler((clamped_rot[0], clamped_rot[1], clamped_rot[2]), "XYZ")
  bone.keyframe_insert(data_path="rotation_euler", frame=frame)
  ```
  * *Audit Finding*: This is the **only legitimate site** in the production pipeline where humanoid trunk bones are rotated and keyframed.
  * *ROM Verification*: Immediately preceded by `enforce_joint_limits()` (line 350) to guarantee zero physiological limit breaches.

### 3.2 Foot IK Target Mutations
* **`src/rig/foot_contact.py:150-158`** (`lock_foot_contact`):
  ```python
  ik_target.location = lock_pos
  ik_target.keyframe_insert(data_path="location", frame=frame)
  ```
  * *Audit Finding*: Invoked exclusively by `WholeBodyController` when a foot is in stance contact. Locks position in world space.
* **`src/rig/ik.py:392-398`** (`set_foot_ik_target`):
  ```python
  ik_target.location = target_location
  if insert_keyframe:
      ik_target.keyframe_insert(data_path="location", frame=frame)
  ```
  * *Audit Finding*: Invoked exclusively by `WholeBodyController` when a foot is in swing phase.

### 3.3 Hand IK Target Mutations
* **`src/rig/arm_ik.py:490-498`** (`set_hand_ik_target`):
  ```python
  hand_target.location = target_location
  if insert_keyframe:
      hand_target.keyframe_insert(data_path="location", frame=frame)
  ```
  * *Audit Finding*: Invoked exclusively by `WholeBodyController` to position hand IK targets during arm swing or reaching.

### 3.4 Root Object Mutations
* **`src/motion/whole_body_controller.py:330-338`**:
  ```python
  character_root.location = targets.root_location
  character_root.rotation_euler = targets.root_rotation
  character_root.keyframe_insert(data_path="location", frame=frame)
  character_root.keyframe_insert(data_path="rotation_euler", frame=frame)
  ```
  * *Audit Finding*: Root translation and yaw rotation are written exclusively by WBC.

---

## 4. Competing Write Risk Analysis & Verification

1. **Direct Bone Manipulation Bypass Check**:
   * *Audit Conclusion*: **ZERO BYPASSES DETECTED**. No motion actions, planners, or bridge executors directly write to `armature.pose.bones`. All pose bone mutations flow strictly through `WholeBodyController._apply_trunk_posture` and `_apply_limb_targets`.
2. **Double Keyframing Risk**:
   * *Audit Conclusion*: **RESOLVED**. In historical prototypes (Task 5B/5C), both the action generator and rig prototype inserted keyframes. In the Phase 7 unified pipeline, keyframing is centralized exclusively inside `WholeBodyController.execute_frame()`.
3. **Foot Stance vs Swing Clamping Conflict**:
   * *Audit Conclusion*: **CONTROLLED**. `WholeBodyController` explicitly checks `targets.left_contact_state.is_support` and `targets.right_contact_state.is_support`. If True, it routes to `lock_foot_contact()`; if False, it routes to `set_foot_ik_target()`. The two branches are mutually exclusive per foot per frame.
