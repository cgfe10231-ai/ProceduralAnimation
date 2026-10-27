# Environment Gate 01 — Repair Unit 2: Counter-Factual Evidence Summary

This report documents the counter-factual verification performed for Repair Unit 2 (BVH Cache Invalidation & Scene Geometry Consistency) under Environment Gate 01.
Each known regression mode (C01, C03, C05) was isolated, injected with its legacy defect mutation into the evaluation runtime, executed headless in Blender 5.1.1 LTS, and verified to cause the exact expected test failure with non-zero exit code (`1`). Restoring production code verified that all tests pass cleanly (`0`).

---

## 1. Defect C01 — Empty Collection Cache Rebuild Leak

### 1.1 Description & Mechanism
- **Target Methods**: `BlenderMeshEnvironmentAdapter.rebuild()`, `BlenderMeshEnvironmentAdapter.refresh()`
- **Defect Hypothesis**: In legacy implementation, `self._bvh` was `None` when target collections contained 0 mesh objects. `refresh()` evaluated `if force or self._dirty or self._bvh is None: self.rebuild()`. Consequently, every subsequent query against an empty environment triggered a full BVH rebuild, executing 100 redundant rebuilds across 100 queries.
- **Injected Mutation**:
  ```python
  def buggy_refresh(self, force=False):
      if force or self._dirty or self._bvh is None:
          self.rebuild()
          return
      if self._check_scene_changed():
          self.rebuild()
  ```

### 1.2 Execution & Evidence
- **Test Command**:
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" -b -P tests/run_counter_factual_ru2.py
  ```
- **Target Test**: `tests/test_mesh_environment_query.py::TestMeshEnvironmentQuery::test_33_c01_empty_environment_cache_reuse_and_addition`
- **Mutated Status**: `FAILURE` (Exit Code 1)
- **Failing Assertion**:
  ```text
  AssertionError: 201 != 1 : Cache rebuild count must remain exactly 1 after 100 empty queries
  ```
- **Production Status**: `PASS` (Exit Code 0, execution time 0.052s, `rebuild_count == 1` after 100 ray queries + 100 nearest queries).
- **Log Artifact**: [`counter_factual_c01_empty_rebuild.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru2/counter_factual_c01_empty_rebuild.log)

---

## 2. Defect C03 — Stale Vertex Coordinates in Path A (Automatic Detection)

### 2.1 Description & Mechanism
- **Target Method**: `BlenderMeshEnvironmentAdapter._check_scene_changed()`
- **Defect Hypothesis**: Legacy `refresh()` inspected only object-level transformation matrices (`obj.matrix_world`). When raw vertex coordinates in `obj.data.vertices` were modified in memory without translating or rotating the parent object, `_check_scene_changed()` returned `False`. The cached BVH tree remained stale and subsequent queries returned outdated spatial intersections.
- **Injected Mutation**:
  ```python
  def buggy_check(self):
      target_objects = self._gather_target_objects()
      current_mesh_objects = [o for o in target_objects if o.type == "MESH" and o.data is not None]
      current_uids = {o.session_uid for o in current_mesh_objects}
      if current_uids != self._tracked_session_uids:
          return True
      for obj in current_mesh_objects:
          uid = obj.session_uid
          snap = self._object_snapshots.get(uid)
          if snap is None or self._matrices_differ(obj.matrix_world, snap.matrix_world):
              return True
      # Deliberately omit vert_hash, loop_hash, and mod_fingerprint checks
      return False
  ```

### 2.2 Execution & Evidence
- **Test Command**:
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" -b -P tests/run_counter_factual_ru2.py
  ```
- **Target Test**: `tests/test_mesh_environment_query.py::TestMeshEnvironmentQuery::test_35_c03_1_vertex_coordinate_movement`
- **Mutated Status**: `FAILURE` (Exit Code 1)
- **Failing Assertion**:
  ```text
  AssertionError: 1 != 2 : Automatic change detection must trigger rebuild
  ```
- **Production Status**: `PASS` (Exit Code 0, execution time 0.049s, `rebuild_count == 2`, hit position correctly updated from 1.0m to 2.25m).
- **Log Artifact**: [`counter_factual_c03_vertex_stale.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru2/counter_factual_c03_vertex_stale.log)

---

## 3. Defect C05 — Stale Collection Membership & Object Rename

### 3.1 Description & Mechanism
- **Target Method**: `BlenderMeshEnvironmentAdapter._check_scene_changed()`
- **Defect Hypothesis**: Legacy `refresh()` iterated only previously tracked object names in `self._tracked_objects`. If new objects were linked into the collection after initial adapter construction, the legacy check never examined candidate objects outside `self._tracked_objects`, failing to trigger a rebuild and causing queries to miss newly added surfaces. Additionally, object renaming broke name lookups.
- **Injected Mutation**:
  ```python
  def buggy_check(self):
      for name in self._tracked_objects:
          obj = bpy.data.objects.get(name)
          if obj is None:
              return True
          snap = self._object_snapshots.get(obj.session_uid)
          if snap is None or self._matrices_differ(obj.matrix_world, snap.matrix_world):
              return True
      return False
  ```

### 3.2 Execution & Evidence
- **Test Command**:
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" -b -P tests/run_counter_factual_ru2.py
  ```
- **Target Test**: `tests/test_mesh_environment_query.py::TestMeshEnvironmentQuery::test_41_c05_collection_membership_lifecycle`
- **Mutated Status**: `FAILURE` (Exit Code 1)
- **Failing Assertion**:
  ```text
  AssertionError: 2 != 1 : Object rename without geometric change must reuse BVH with 0 rebuilds
  ```
- **Production Status**: `PASS` (Exit Code 0, execution time 0.050s, `rebuild_count == 1` after rename, `rebuild_count == 2` after new mesh linked to collection).
- **Log Artifact**: [`counter_factual_c05_collection_membership_stale.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru2/counter_factual_c05_collection_membership_stale.log)

---

## 4. Counter-Factual Verification Matrix

| Defect ID | Defect Category | Target Production Method | Mutated Legacy Behavior | Exit Code (Mutated) | Exit Code (Production) | Evidence Artifact |
|---|---|---|---|---|---|---|
| **C01** | Empty Cache Leak | `refresh()`, `rebuild()` | `_bvh is None` forces rebuild on every query | `1` (FAIL) | `0` (PASS) | [`counter_factual_c01_empty_rebuild.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru2/counter_factual_c01_empty_rebuild.log) |
| **C03** | Stale Vertex Geometry | `_check_scene_changed()` | Only checks translation matrix, ignores vertex coordinates | `1` (FAIL) | `0` (PASS) | [`counter_factual_c03_vertex_stale.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru2/counter_factual_c03_vertex_stale.log) |
| **C05** | Collection Scope & Rename | `_check_scene_changed()` | Iterates only `_tracked_objects` names, misses new members | `1` (FAIL) | `0` (PASS) | [`counter_factual_c05_collection_membership_stale.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru2/counter_factual_c05_collection_membership_stale.log) |
