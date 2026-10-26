# ProceduralAnimation: Hardcode & Bypass Audit (7A→7B Gate)

> **Document Status**: COMPLETED ARCHITECTURE AUDIT BASELINE  
> **Target Milestone**: Admission Gate Phase 7A → Phase 7B  
> **Audit Date**: 2026-10-27  
> **Git Reference**: `670766a26fa7b2ba1f8feee609625d01de98cd39`  

---

## 1. Audit Taxonomy of Hardcodes & Bypasses

To separate legitimate domain constants from brittle shortcuts and architectural violations, this audit categorizes all discovered constants, magic numbers, string couplings, and direct manipulations into six strict categories:

* **Category A: Legitimate Physiological & Physical Constants** (Biomechanical constants, physical laws)
* **Category B: Standard Engineering Configurations** (Frame rates, seeds, rendering resolution, tolerances)
* **Category C: Test Fixtures & Milestone Benchmark Profiles** (Standard 204-frame reference sequences)
* **Category D: Unreasonable Scene Object Couplings** (Hardcoded Blender object names, collection strings)
* **Category E: Illegal Hardcoding & Magic Frame Number Logic** (Hardcoded frame splits, coordinate jumps)
* **Category F: Architectural Bypasses** (Direct bone manipulations bypassing WBC or IK)

---

## 2. Category A: Legitimate Physiological & Physical Constants

These constants represent verified physical laws, anthropometric literature standards, and anatomical limits. They are sound and mathematically justified.

| Module & Line | Symbol / Constant | Value | Physical Justification |
| :--- | :--- | :--- | :--- |
| `src/motion/rigid_link.py:148-230` | `DEMPSTER_WINTER_15_SEGMENT_MODEL` | Mass fractions summing to 1.0 (70kg total) | Dempster-Winter biomechanical body segment mass distribution model. |
| `src/motion/joint_limits.py:264-390` | `DEFAULT_HUMANOID_ROM_MODEL` | Min/max angles for 19 joints | Human anatomical Range of Motion limits (Kapandji / Winter clinical data). |
| `src/motion/forward_dynamics.py:460` | Gravity vector $g$ | `(0.0, 0.0, -9.81)` $m/s^2$ | Standard Earth gravitational acceleration in SI units. |
| `src/motion/contact_dynamics.py:410` | Default friction $\mu$ | $0.6$ (dimensionless) | Standard dry rubber-to-concrete Coulomb friction coefficient. |
| `src/rig/ik.py:45` | `ANKLE_REST_Z` | $0.12$ m | Anatomical distance from foot sole contact to ankle joint center. |
| `src/rig/ik.py:46` | `HIP_X_OFFSET` | $0.15$ m | Lateral offset from pelvis center to hip joint centers. |

* **Verdict**: **APPROVED & SOUND**.

---

## 3. Category B: Standard Engineering Configurations

These constants configure pipeline execution, solver tolerances, and output formats.

| Module & Line | Configuration Parameter | Value | Audit Assessment |
| :--- | :--- | :--- | :--- |
| `src/config.py:18` | `fps` | $24$ | Industry standard animation frame rate. |
| `src/config.py:19` | `random_seed` | $42$ | Seed guaranteeing 100% deterministic reproducibility. |
| `src/config.py:22` | `render_resolution` | `(1920, 1080)` | Standard 1080p visual verification output. |
| `src/motion/contact_force_solver.py:175` | `max_iterations` | $200$ | QP solver iteration cap to guarantee real-time convergence. |
| `src/motion/joint_limits.py:430` | `clamping_tolerance` | $10^{-4}$ rad | Numerical boundary tolerance to avoid floating-point jitter. |

* **Verdict**: **APPROVED & SOUND**.

---

## 4. Category C: Test Fixtures & Milestone Benchmark Profiles

Constants defining reference test suites and regression trajectories.

| Module & Line | Test Fixture | Value | Purpose |
| :--- | :--- | :--- | :--- |
| `src/motion/framework.py:450-480` | `StartStopWalkAction` frame ranges | Total 204 frames (1-24 idle, 25-60 accel, 61-144 walk, 145-180 decel, 181-204 rest) | Historical flat-ground locomotion benchmark verified across Tasks 5C, 6A, 6G-D, and 7A-1. |
| `src/motion/framework.py:465` | Target walking speed | $1.2$ m/s | Standard human comfortable walking speed. |
| `src/scene/layout.py:45-80` | `generate_environment_layout` | Building & pillar bounds | Spatial corridor clearance test fixtures for Task 3. |

* **Verdict**: **APPROVED (Valid for benchmarks; must not leak into generic dynamic actions)**.

---

## 5. Category D: Unreasonable Scene Object Couplings

Brittle couplings where code relies on specific string names of Blender objects or collections.

| Module & Line | Hardcoded String | Context | Audit Risk Assessment |
| :--- | :--- | :--- | :--- |
| `src/character/builder.py:18` | `"CharacterRoot"`, `"CharacterArmature"` | Root object names | Moderate. Acceptable as canonical character identifiers, but breaks if multiple characters are instantiated. |
| `src/rig/ik.py:120` | `"FootIK.L"`, `"FootIK.R"`, `"KneePole.L"`, `"KneePole.R"` | Empty controller names | Moderate. Rig constraints directly target these literal string names. |
| `src/rig/arm_ik.py:145` | `"HandIK.L"`, `"HandIK.R"`, `"ElbowPole.L"`, `"ElbowPole.R"` | Empty controller names | Moderate. Rig constraints directly target these literal string names. |
| `src/scene/builder.py:280-340` | `"Terrain_Ground"`, `"Terrain_Ramp"`, `"Terrain_Platform"` | Mesh object names | **HIGH RISK in historical 7A-2**. In early 7A-2 drafts, planners checked if the character was standing on `"Terrain_Ramp"`. This was **eliminated in Task 7A-2 Correction** in favor of numerical elevation queries $Z(x, y)$ in `DynamicsEnvironmentQuery`. |

* **Remediation Status**:
  * Terrain name string checks were **completely removed** in Task 7A-2 Correction (`670766a`).
  * Empty controller string names remain standard practice for single-character Blender rigs, but should be encapsulated behind a rig naming registry in Phase 7C.

---

## 6. Category E: Illegal Hardcoding & Magic Frame Logic

This category audits logic that hardcodes specific frame numbers or spatial jumps instead of computing dynamic trajectories.

### The Historical Frame 226 $\to$ 227 Spatial Teleport Defect (Audited & Closed)
* **Location in Failed Draft**: Historical `src/scene/playground_terrain_traversal.py` (before commit `670766a`).
* **Mechanism of Failure**: At frame 226, the historical script had an uncoordinated state handoff between two spliced action clips, causing `CharacterRoot` to instantly teleport $+1.0m$ in $Y$ and $+0.25m$ in $Z$ over 1 frame ($v_y = 24.0 m/s$, acceleration $> 500 m/s^2$).
* **Correction in Commit `670766a`**: Splicing was eliminated. A single unified `TerrainWalkAction` now plans the entire continuous trajectory from frame 1 to 280, maintaining $C^0$ position and $C^1$ velocity continuity across all surface transitions.
* **Regression Protection**: Enforced by dedicated automated test `tests/test_p0_frame226_teleport_regression.py`.

### Residual Hardcoding in Traversal Waypoints
* **Location**: `src/scene/playground_terrain_traversal.py:195-205`
* **Finding**: Route waypoints are hardcoded coordinates:
  ```python
  waypoints = [
      (0.0, 0.0),      # Flat ground start
      (0.0, 4.0),      # Ramp entrance
      (0.0, 8.0),      # Platform entrance
      (0.0, 12.0),     # Platform traversal
  ]
  ```
* **Audit Assessment**: Acceptable as a fixed scene test route for Task 7A-2, but in Phase 7B/7C, route waypoints must be dynamically generated from path planners or navigation meshes.

---

## 7. Category F: Architectural Bypass Audit

An exhaustive search was conducted across all files in `src/` for illegal direct manipulations of `CharacterArmature.pose.bones`:

```
Pattern: pose.bones[...].(location|rotation_euler|keyframe_insert)
```

### Audit Findings:
1. **`src/motion/whole_body_controller.py`**:
   * Lines 357-368: Direct write to `pose.bones[bone_name].rotation_euler` and `keyframe_insert`.
   * *Assessment*: **LEGITIMATE**. `WholeBodyController` is the single designated exclusive pose bone writer.
2. **`src/rig/pose.py`**:
   * Lines 32, 48: Low-level utility functions.
   * *Assessment*: **CONTROLLED**. Only called internally by `WholeBodyController`.
3. **All Other Modules (`src/motion/framework.py`, `src/motion/terrain_walk.py`, `src/motion/kinematic_bridge.py`, etc.)**:
   * *Assessment*: **ZERO DIRECT BONE WRITES FOUND**. All actions route strictly through `KinematicBridgeExecutor` $\to$ `WholeBodyController`.

* **Verdict**: **NO ACTIVE BYPASSES EXIST IN THE PRODUCTION PIPELINE**.
