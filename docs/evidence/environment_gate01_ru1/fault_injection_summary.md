# Environment Gate 01 — Repair Unit 1: Fault Injection Evidence Summary

This report documents the real fault injection verification performed for Repair Unit 1 under Environment Gate 01.
Each known regression mode (A03, A01, A02) was dynamically injected into the evaluation runtime, executed headless in Blender 5.1.1 LTS, and verified to cause the exact expected test failure with non-zero exit code (`1`). Restoring the production code verified that all tests pass (`0`).

---

## 1. Fault Injection Case A03 — Collection Scope Bleed

### 1.1 Description & Mechanism
- **Target Method**: `BlenderMeshEnvironmentAdapter._gather_target_objects(self)`
- **Defect Hypothesis**: If collection filtering logic fails or falls back improperly, objects outside the specified `collection_names` will bleed into the spatial adapter and BVH tree, contaminating queries with unapproved scene meshes.
- **Injected Mutation**:
  ```python
  def buggy_gather(self):
      # Buggy mutation: ignore self._collection_names and gather all scene meshes
      return [obj for obj in self._scene.objects if obj.type == 'MESH']
  BlenderMeshEnvironmentAdapter._gather_target_objects = buggy_gather
  ```

### 1.2 Execution & Evidence
- **Test Command**:
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" -b --python-expr <A03_MUTATION_RUNNER>
  ```
- **Target Test**: `tests/test_mesh_environment_query.py::TestMeshEnvironmentQuery::test_11_a03_3_collection_isolation`
- **Exit Code**: `1` (Failure cleanly trapped)
- **Failing Assertion**:
  ```text
  Traceback (most recent call last):
    File "tests/test_mesh_environment_query.py", line 502, in test_11_a03_3_collection_isolation
      self.assertNotIn("Surface_Forbidden", adapter.tracked_objects)
  AssertionError: 'Surface_Forbidden' unexpectedly found in ['Surface_Allowed', 'Surface_Forbidden']
  ```
- **Log Artifact**: [`fault_injection_a03.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru1/fault_injection_a03.log)
- **Production Validation**: With production scoping rules restored, `test_11` passes, confirming complete isolation of `Surface_Forbidden`.

---

## 2. Fault Injection Case A01 — Raycast Filter Bypass

### 2.1 Description & Mechanism
- **Target Method**: `BlenderMeshEnvironmentAdapter.ray_cast(self, origin, direction, distance, surface_type_filter, ...)`
- **Defect Hypothesis**: If the raycast implementation ignores `surface_type_filter` and simply returns the first physical surface hit (pre-Repair Unit 1 bug), queries for lower/background surfaces obscured by a foreground obstacle will return the wrong foreground surface instead of advancing past it.
- **Injected Mutation**:
  ```python
  def buggy_ray_cast(self, origin, direction, distance=10.0, surface_type_filter=None, **kwargs):
      # Buggy mutation: strip surface_type_filter and perform single unfiltered nearest cast
      return orig_ray_cast(self, origin, direction, distance=distance, surface_type_filter=None)
  BlenderMeshEnvironmentAdapter.ray_cast = buggy_ray_cast
  ```

### 2.2 Execution & Evidence
- **Test Command**:
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" -b --python-expr <A01_MUTATION_RUNNER>
  ```
- **Target Test**: `tests/test_mesh_environment_query.py::TestMeshEnvironmentQuery::test_14_a01_2_ray_filtered_finds_second_surface`
- **Exit Code**: `1` (Failure cleanly trapped)
- **Failing Assertion**:
  ```text
  Traceback (most recent call last):
    File "tests/test_mesh_environment_query.py", line 619, in test_14_a01_2_ray_filtered_finds_second_surface
      self._assert_surface_contract(...)
    File "tests/test_mesh_environment_query.py", line 361, in _assert_surface_contract
      self.assertIn(expected_id_substr, res.surface_id)
  AssertionError: 'Ground_Back' not found in 'mesh:Box_Front:5'
  ```
- **Log Artifact**: [`fault_injection_a01.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru1/fault_injection_a01.log)
- **Production Validation**: With iterative ray advancing restored, `test_14` passes, correctly skipping `Box_Front` at $Z=5.0\text{ m}$ to reach `Ground_Back` at $Z=2.0\text{ m}$.

---

## 3. Fault Injection Case A02 — Nearest Filter Bypass

### 3.1 Description & Mechanism
- **Target Method**: `BlenderMeshEnvironmentAdapter.find_nearest(self, point_world, max_distance, surface_type_filter)`
- **Defect Hypothesis**: If `find_nearest` ignores `surface_type_filter` and returns the closest geometric polygon regardless of surface type (pre-Repair Unit 1 bug), queries for a specific surface class (e.g. `horizontal_ground`) will return a closer non-matching obstacle (e.g. `box_top`).
- **Injected Mutation**:
  ```python
  def buggy_find_nearest(self, point_world, max_distance=10.0, surface_type_filter=None):
      # Buggy mutation: strip surface_type_filter and return closest polygon unconditionally
      return orig_find_nearest(self, point_world, max_distance=max_distance, surface_type_filter=None)
  BlenderMeshEnvironmentAdapter.find_nearest = buggy_find_nearest
  ```

### 3.2 Execution & Evidence
- **Test Command**:
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" -b --python-expr <A02_MUTATION_RUNNER>
  ```
- **Target Test**: `tests/test_mesh_environment_query.py::TestMeshEnvironmentQuery::test_20_a02_2_nearest_filtered_finds_target_surface`
- **Exit Code**: `1` (Failure cleanly trapped)
- **Failing Assertion**:
  ```text
  Traceback (most recent call last):
    File "tests/test_mesh_environment_query.py", line 793, in test_20_a02_2_nearest_filtered_finds_target_surface
      self._assert_surface_contract(...)
    File "tests/test_mesh_environment_query.py", line 361, in _assert_surface_contract
      self.assertIn(expected_id_substr, res.surface_id)
  AssertionError: 'Plane_Far' not found in 'mesh:Box_Near:5'
  ```
- **Log Artifact**: [`fault_injection_a02.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru1/fault_injection_a02.log)
- **Production Validation**: With polygon-level metadata filtering restored, `test_20` passes, correctly rejecting `Box_Near` at distance $0.2\text{ m}$ to select `Plane_Far` at distance $0.8\text{ m}$.

---

## 4. Summary Matrix of Fault Injections

| Fault ID | Target Mechanism | Injected Mutation | Trapped Test | Exit Code | Verified Failure Reason | Restored State |
|:---------|:-----------------|:------------------|:-------------|:---------:|:------------------------|:--------------:|
| **A03** | Collection Isolation | Bypass `collection_names` | `test_11` | `1` | `Surface_Forbidden` bled into tracked objects | **PASS (`0`)** |
| **A01** | Raycast Surface Filter | Strip `surface_type_filter` | `test_14` | `1` | Hit `Box_Front` instead of `Ground_Back` | **PASS (`0`)** |
| **A02** | Nearest Surface Filter | Strip `surface_type_filter` | `test_20` | `1` | Hit `Box_Near` instead of `Plane_Far` | **PASS (`0`)** |
