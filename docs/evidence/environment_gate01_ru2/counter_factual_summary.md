# Environment Gate 01 — Repair Unit 2: Counter-Factual Evidence Summary

This report documents the counter-factual verification performed for Repair Unit 2 (BVH Cache Invalidation, Scene Geometry Consistency & Exception Safety Hardening) under Environment Gate 01.
Each known regression mode (C01, C03, C05, F01, F02, F03) was isolated, injected with its legacy defect mutation into the evaluation runtime, executed headless in Blender 5.1.1 LTS, and verified to cause the exact expected test failure with non-zero exit code (`1`). Restoring production code verified that all tests pass cleanly (`0`).

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

## 4. Defect F01 — Collection Member Retention Leak (Unlinking Ignored)

### 4.1 Description & Mechanism
- **Target Method**: `BlenderMeshEnvironmentAdapter._check_scene_changed()`
- **Defect Hypothesis**: If candidate membership change detection only checked whether current objects are a subset of previously tracked objects (`current_uids.issubset(self._tracked_session_uids)`), unlinking an object from an allowed collection without deleting it from `bpy.data.objects` would fail to trigger a rebuild. The unlinked object would mistakenly remain in the compiled BVH tree, returning ghost hits on objects no longer in the allowed collection.
- **Injected Mutation**:
  ```python
  def buggy_check_f01(self):
      target_objects = self._gather_target_objects()
      current_mesh_objects = [o for o in target_objects if o.type == "MESH" and o.data is not None]
      current_uids = {o.session_uid for o in current_mesh_objects}
      # Mutated: only check issubset (ignores unlinked members leaving the collection)
      if not current_uids.issubset(self._tracked_session_uids):
          return True
      # Checks snapshots only for remaining objects
      for obj in current_mesh_objects:
          snap = self._object_snapshots.get(obj.session_uid)
          if snap is None or self._matrices_differ(obj.matrix_world, snap.matrix_world):
              return True
      return False
  ```

### 4.2 Execution & Evidence
- **Test Command**:
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" -b -P tests/run_counter_factual_ru2.py
  ```
- **Target Test**: `tests/test_mesh_environment_query.py::TestMeshEnvironmentQuery::test_43_c05_1_collection_member_unlinked`
- **Mutated Status**: `FAILURE` (Exit Code 1)
- **Failing Assertion**:
  ```text
  AssertionError: True is not false : Unlinked Surface_A must no longer be hit by query
  ```
- **Production Status**: `PASS` (Exit Code 0, execution time 0.051s, `current_uids != self._tracked_session_uids` triggers exactly 1 rebuild, unlinked object removed from query results).
- **Log Artifact**: [`counter_factual_f01_member_retention_leak.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru2/counter_factual_f01_member_retention_leak.log)

---

## 5. Defect F02 — Valid Empty BVH Repeated Rebuild Leak

### 5.1 Description & Mechanism
- **Target Methods**: `BlenderMeshEnvironmentAdapter.refresh()`, `BlenderMeshEnvironmentAdapter.rebuild()`
- **Defect Hypothesis**: If `refresh()` uses `self._bvh is None` as an indicator of an unbuilt or invalid cache, transitioning a collection from non-empty to empty leaves `_bvh = None`. Every subsequent query against the empty collection triggers a full rebuild, executing 100 redundant rebuilds across 100 queries instead of reusing the `VALID_EMPTY` state.
- **Injected Mutation**:
  ```python
  def buggy_refresh_f02(self, force=False):
      if force or self._dirty or self._bvh is None:
          self.rebuild()
          return
      if self._check_scene_changed():
          self.rebuild()
  ```

### 5.2 Execution & Evidence
- **Test Command**:
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" -b -P tests/run_counter_factual_ru2.py
  ```
- **Target Test**: `tests/test_mesh_environment_query.py::TestMeshEnvironmentQuery::test_45_c05_3_non_empty_to_empty_transition_and_reuse`
- **Mutated Status**: `FAILURE` (Exit Code 1)
- **Failing Assertion**:
  ```text
  AssertionError: 102 != 2 : Zero rebuilds allowed across 100 empty queries
  ```
- **Production Status**: `PASS` (Exit Code 0, execution time 0.050s, `rebuild_count == 2` across 100 empty queries, returns `success=False` with `source_type="none"`, recovers cleanly to `rebuild_count == 3` when mesh added).
- **Log Artifact**: [`counter_factual_f02_empty_bvh_repeated_rebuild.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru2/counter_factual_f02_empty_bvh_repeated_rebuild.log)

---

## 6. Defect F03 — Exception Mid-Flight Residual in REBUILDING

### 6.1 Description & Mechanism
- **Target Method**: `BlenderMeshEnvironmentAdapter.rebuild()`
- **Defect Hypothesis**: If `self._cache_state = AdapterCacheState.REBUILDING` is set before entering the `try:` block, and an unhandled exception is raised during target object candidate gathering (`self._gather_target_objects()`), the exception bypasses the `except Exception:` rollback block. The adapter remains permanently stuck in `AdapterCacheState.REBUILDING`, corrupting all future queries.
- **Injected Mutation**:
  ```python
  def buggy_rebuild_f03(self):
      self._cache_state = AdapterCacheState.REBUILDING
      # Mutated: gather outside try/except block
      target_objects = self._gather_target_objects()
      if getattr(self, "_inject_gather_error", False):
          raise RuntimeError("Simulated gather candidate error")
      try:
          ...
      except Exception as e:
          self._cache_state = AdapterCacheState.FAILED
          self._dirty = True
          raise
  ```

### 6.2 Execution & Evidence
- **Test Command**:
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" -b -P tests/run_counter_factual_ru2.py
  ```
- **Target Test**: `tests/test_mesh_environment_query.py::TestMeshEnvironmentQuery::test_47_c06_rebuild_exception_safety`
- **Mutated Status**: `FAILURE` (Exit Code 1)
- **Failing Assertion**:
  ```text
  AssertionError: <AdapterCacheState.REBUILDING: 'rebuilding'> != <AdapterCacheState.FAILED: 'failed'>
  ```
- **Production Status**: `PASS` (Exit Code 0, execution time 0.051s, transitions to `AdapterCacheState.FAILED`, marks `_dirty = True`, releases evaluated meshes in `finally:`, and recovers self-healing on next query).
- **Log Artifact**: [`counter_factual_f03_exception_state_residual.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru2/counter_factual_f03_exception_state_residual.log)

---

## 7. Counter-Factual Verification Matrix

| Defect ID | Defect Category | Target Production Method | Mutated Legacy Behavior | Exit Code (Mutated) | Exit Code (Production) | Evidence Artifact |
|---|---|---|---|---|---|---|
| **C01** | Empty Cache Leak | `refresh()`, `rebuild()` | `_bvh is None` forces rebuild on every query | `1` (FAIL) | `0` (PASS) | [`counter_factual_c01_empty_rebuild.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru2/counter_factual_c01_empty_rebuild.log) |
| **C03** | Stale Vertex Geometry | `_check_scene_changed()` | Only checks translation matrix, ignores vertex coordinates | `1` (FAIL) | `0` (PASS) | [`counter_factual_c03_vertex_stale.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru2/counter_factual_c03_vertex_stale.log) |
| **C05** | Collection Scope & Rename | `_check_scene_changed()` | Iterates only `_tracked_objects` names, misses new members | `1` (FAIL) | `0` (PASS) | [`counter_factual_c05_collection_membership_stale.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru2/counter_factual_c05_collection_membership_stale.log) |
| **F01** | Member Retention Leak | `_check_scene_changed()` | Only checks subset, ignores unlinked members leaving collection | `1` (FAIL) | `0` (PASS) | [`counter_factual_f01_member_retention_leak.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru2/counter_factual_f01_member_retention_leak.log) |
| **F02** | Empty BVH Repeated Rebuild | `refresh()` | Uses `_bvh is None` instead of state machine, causing repeated rebuilds | `1` (FAIL) | `0` (PASS) | [`counter_factual_f02_empty_bvh_repeated_rebuild.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru2/counter_factual_f02_empty_bvh_repeated_rebuild.log) |
| **F03** | Exception Stuck in Rebuilding | `rebuild()` | Gather outside `try:` block leaves state stuck in `REBUILDING` | `1` (FAIL) | `0` (PASS) | [`counter_factual_f03_exception_state_residual.log`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru2/counter_factual_f03_exception_state_residual.log) |
