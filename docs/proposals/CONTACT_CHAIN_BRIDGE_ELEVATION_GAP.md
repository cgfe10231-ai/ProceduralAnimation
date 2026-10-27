# Architecture Proposal: KinematicBridge Foot Contact Elevation Discrepancy & 3D Contact Semantics

> **Document Status**: SUBSEQUENT GATE PROPOSAL (AWAITING SEPARATE AUTHORIZATION)  
> **Source Task**: Environment Gate 01  
> **Target Subsystem**: `src/motion/kinematic_bridge.py`  
> **Defect Reproduction Test**: `tests/test_contact_elevation_gap_repro.py`  
> **Execution Constraint**: PURE PROPOSAL — ZERO PRODUCTION CONTROL CHAIN CODE MODIFIED IN THIS GATE  

---

## 1. Defect Analysis & Root Cause

During the static and dynamic audit of `src/motion/kinematic_bridge.py`, an elevation flattening defect was discovered in the foot contact evaluation pathway.

### 1.1 Physical Code Defect Location
In `src/motion/kinematic_bridge.py:401-408`:
```python
# Foot contact intent & locking
for side, ft in [("L", planned.foot_L), ("R", planned.foot_R)]:
    limb_key = f"foot_{side}"
    if ft.is_locked:
        active_limb_targets[limb_key] = {
            "surface_id": ft.surface_id,
            "target_world": (ft.world_xyz[0], ft.world_xyz[1], 0.0),  # <-- DEFECT: Z flattened to 0.0
            "normal_world": ft.normal_world,
            "contact_type": ft.contact_type,
            "lifecycle": ContactLifecycle.ESTABLISHED,
        }
```
In parallel, lines 388-394 hardcode:
```python
surfaces = [
    EnvironmentalSurface(
        surface_id="ground",
        surface_type="ground",
        center_world=(0.0, 0.0, 0.0),
        normal_world=(0.0, 0.0, 1.0),
    )
]
```

### 1.2 Impact on 3D Complex Terrain Locomotion
1. **Target Elevation Mismatch**:
   When a foot is locked on an elevated surface (e.g. the Bridge Platform at $Z = 1.3397\text{ m}$ or a stair tread at $Z = 0.45\text{ m}$), `ft.world_xyz` carries the correct 3D world position $(x, y, 1.3397)$.
   However, `active_limb_targets[limb_key]["target_world"]` forcibly replaces the $Z$ component with `0.0`.
2. **Contact Telemetry Invalidation**:
   When `evaluate_limb_contacts_from_armature` runs, it measures the foot distance against `(x, y, 0.0)`. For an elevated stance foot at $Z = 1.3397\text{ m}$, the contact model registers an artificial error of $\Delta Z = 1.3397\text{ m} \gg 0.015\text{ m}$ (tolerance), misclassifying the established contact or computing erroneous penetration distances.
3. **Single Surface Blindness**:
   `surfaces` only contains a single horizontal plane at $Z = 0.0\text{ m}$. Contact geometric validation against ramps, stairs, and elevated boxes is entirely bypassed because the bridge does not forward the environment's true surfaces.

---

## 2. Machine-Verifiable Reproduction Evidence

An isolated regression test [`tests/test_contact_elevation_gap_repro.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_contact_elevation_gap_repro.py) was constructed and executed in headless Blender:

```
======================================================================
CONTACT ELEVATION GAP REPRODUCTION EVIDENCE:
  Planned Stance Foot Contact Z: 1.3397 m (Elevated Platform)
  KinematicBridge Line 404 Target Z: 0.0000 m (Hardcoded Flat Ground)
  Elevation Error Discrepancy:   1.3397 m
======================================================================
```
* **Exit Code**: 0 (Defect reliably verified and asserted).
* **Observation**: The planned contact at $Z = 1.3397\text{ m}$ is flattened to $0.0\text{ m}$, creating a $1.3397\text{ m}$ target error.

---

## 3. Minimal Change Proposal (For Subsequent Gate)

To resolve this defect without introducing unintended regressions or altering the human control chain during Environment Gate 01, the following minimal, targeted modifications are proposed for a dedicated subsequent gate (e.g., `Contact Chain Elevation Gate`):

### 3.1 Modification A: Preserve Planned Stance Foot Z Coordinate
In `src/motion/kinematic_bridge.py:404`:
```diff
- "target_world": (ft.world_xyz[0], ft.world_xyz[1], 0.0),
+ "target_world": (ft.world_xyz[0], ft.world_xyz[1], ft.world_xyz[2]),
```

### 3.2 Modification B: Dynamically Forward Environmental Surfaces
In `KinematicBridgeExecutor.__init__`:
* Accept an optional `environment: Optional[DynamicsEnvironmentQuery] = None`.
* If provided, derive `surfaces` from `environment.get_all_surfaces()` or the attached `BlenderMeshEnvironmentAdapter`, rather than instantiating a hardcoded single ground plane at `(0, 0, 0)`.

### 3.3 Acceptance Criteria for Subsequent Gate
1. Stance contacts on platforms ($Z > 0.0\text{ m}$) maintain `target_world[2] == ft.world_xyz[2]` with $\Delta Z < 10^{-6}\text{ m}$.
2. `ContactRecord` penetration and gap distances are evaluated against the true local surface (e.g., elevated platform or ramp incline).
3. All existing flat-ground tests (`quick`, `motion`, `full`) remain 100% green with zero regression.

---

## 4. Current Task Boundary & Safeguards

In strict compliance with Environment Gate 01 instructions:
* **No changes have been made to `KinematicBridgeExecutor` or `ContactModel` in this task.**
* The human control chain remains 100% unaltered.
* This proposal is logged as a prerequisite entry gate for full 3D contact closed-loop feedback in Phase 7B.
