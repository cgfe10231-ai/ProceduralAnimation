"""Counter-Factual Evidence Generator for Environment Gate 01 - Repair Unit 2 Final Closure.

Executes fault injection mutations against BlenderMeshEnvironmentAdapter to prove:
1. Under old / mutated logic, tests cleanly FAIL with exit code 1.
2. Under production logic, tests cleanly PASS with exit code 0.
Generates verified evidence logs in docs/evidence/environment_gate01_ru2/.
"""

import io
import os
import sys
import unittest

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import bpy
from src.scene.blender_mesh_query_adapter import (
    AdapterCacheState,
    BlenderMeshEnvironmentAdapter,
)
from tests.test_mesh_environment_query import TestMeshEnvironmentQuery

EVIDENCE_DIR = os.path.join(repo_root, "docs", "evidence", "environment_gate01_ru2")
os.makedirs(EVIDENCE_DIR, exist_ok=True)


def run_case_c01() -> bool:
    """Case C01: Empty collection repeated rebuild leak."""
    log_path = os.path.join(EVIDENCE_DIR, "counter_factual_c01_empty_rebuild.log")
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)

    orig_refresh = BlenderMeshEnvironmentAdapter.refresh

    def buggy_refresh(self, force=False):
        if force or self._dirty or self._bvh is None:
            self.rebuild()
            return
        if self._check_scene_changed():
            self.rebuild()

    BlenderMeshEnvironmentAdapter.refresh = buggy_refresh

    suite = unittest.TestSuite()
    suite.addTest(TestMeshEnvironmentQuery("test_33_c01_empty_environment_cache_reuse_and_addition"))
    mutated_res = runner.run(suite)
    mutated_output = stream.getvalue()

    BlenderMeshEnvironmentAdapter.refresh = orig_refresh
    stream_prod = io.StringIO()
    runner_prod = unittest.TextTestRunner(stream=stream_prod, verbosity=2)
    suite_prod = unittest.TestSuite()
    suite_prod.addTest(TestMeshEnvironmentQuery("test_33_c01_empty_environment_cache_reuse_and_addition"))
    prod_res = runner_prod.run(suite_prod)
    prod_output = stream_prod.getvalue()

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("=== COUNTER-FACTUAL VERIFICATION LOG: DEFECT C01 (EMPTY REBUILD LEAK) ===\n")
        f.write("TARGET DEFECT: C01 (Repeated rebuilds on empty environment due to _bvh is None)\n")
        f.write("MUTATION: Restored legacy refresh condition `if force or self._dirty or self._bvh is None: self.rebuild()`\n\n")
        f.write("--- PHASE 1: MUTATED / LEGACY EXECUTION (EXPECTED FAILURE) ---\n")
        f.write(f"EXIT STATUS: {'FAILURE' if not mutated_res.wasSuccessful() else 'UNEXPECTED PASS'}\n")
        f.write(f"FAILURES COUNT: {len(mutated_res.failures)}\n")
        f.write(mutated_output)
        f.write("\n--- PHASE 2: PRODUCTION LOGIC RESTORED (EXPECTED PASS) ---\n")
        f.write(f"EXIT STATUS: {'PASS' if prod_res.wasSuccessful() else 'FAIL'}\n")
        f.write(prod_output)

    print(f"Case C01 logged to {log_path}. Mutated failed: {not mutated_res.wasSuccessful()}, Prod passed: {prod_res.wasSuccessful()}")
    return (not mutated_res.wasSuccessful()) and prod_res.wasSuccessful()


def run_case_c03() -> bool:
    """Case C03: Stale vertex coordinate change in Path A."""
    log_path = os.path.join(EVIDENCE_DIR, "counter_factual_c03_vertex_stale.log")
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)

    orig_check = BlenderMeshEnvironmentAdapter._check_scene_changed

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
        return False

    BlenderMeshEnvironmentAdapter._check_scene_changed = buggy_check

    suite = unittest.TestSuite()
    suite.addTest(TestMeshEnvironmentQuery("test_35_c03_1_vertex_coordinate_movement"))
    mutated_res = runner.run(suite)
    mutated_output = stream.getvalue()

    BlenderMeshEnvironmentAdapter._check_scene_changed = orig_check
    stream_prod = io.StringIO()
    runner_prod = unittest.TextTestRunner(stream=stream_prod, verbosity=2)
    suite_prod = unittest.TestSuite()
    suite_prod.addTest(TestMeshEnvironmentQuery("test_35_c03_1_vertex_coordinate_movement"))
    prod_res = runner_prod.run(suite_prod)
    prod_output = stream_prod.getvalue()

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("=== COUNTER-FACTUAL VERIFICATION LOG: DEFECT C03 (STALE VERTEX COORDS IN PATH A) ===\n")
        f.write("TARGET DEFECT: C03 (Failure to detect vertex coordinate modification without invalidate())\n")
        f.write("MUTATION: Removed vert_hash check from _check_scene_changed, checking only matrix_world\n\n")
        f.write("--- PHASE 1: MUTATED / LEGACY EXECUTION (EXPECTED FAILURE) ---\n")
        f.write(f"EXIT STATUS: {'FAILURE' if not mutated_res.wasSuccessful() else 'UNEXPECTED PASS'}\n")
        f.write(f"FAILURES COUNT: {len(mutated_res.failures)}\n")
        f.write(mutated_output)
        f.write("\n--- PHASE 2: PRODUCTION LOGIC RESTORED (EXPECTED PASS) ---\n")
        f.write(f"EXIT STATUS: {'PASS' if prod_res.wasSuccessful() else 'FAIL'}\n")
        f.write(prod_output)

    print(f"Case C03 logged to {log_path}. Mutated failed: {not mutated_res.wasSuccessful()}, Prod passed: {prod_res.wasSuccessful()}")
    return (not mutated_res.wasSuccessful()) and prod_res.wasSuccessful()


def run_case_c05() -> bool:
    """Case C05: Collection membership addition detection & rename without rebuild."""
    log_path = os.path.join(EVIDENCE_DIR, "counter_factual_c05_collection_membership_stale.log")
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)

    orig_check = BlenderMeshEnvironmentAdapter._check_scene_changed

    def buggy_check(self):
        for name in self._tracked_objects:
            obj = bpy.data.objects.get(name)
            if obj is None:
                return True
            snap = self._object_snapshots.get(obj.session_uid)
            if snap is None or self._matrices_differ(obj.matrix_world, snap.matrix_world):
                return True
        return False

    BlenderMeshEnvironmentAdapter._check_scene_changed = buggy_check

    suite = unittest.TestSuite()
    suite.addTest(TestMeshEnvironmentQuery("test_41_c05_collection_membership_lifecycle"))
    mutated_res = runner.run(suite)
    mutated_output = stream.getvalue()

    BlenderMeshEnvironmentAdapter._check_scene_changed = orig_check
    stream_prod = io.StringIO()
    runner_prod = unittest.TextTestRunner(stream=stream_prod, verbosity=2)
    suite_prod = unittest.TestSuite()
    suite_prod.addTest(TestMeshEnvironmentQuery("test_41_c05_collection_membership_lifecycle"))
    prod_res = runner_prod.run(suite_prod)
    prod_output = stream_prod.getvalue()

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("=== COUNTER-FACTUAL VERIFICATION LOG: DEFECT C05 (STALE COLLECTION MEMBERSHIP) ===\n")
        f.write("TARGET DEFECT: C05 (Failure to detect new objects added to target collection)\n")
        f.write("MUTATION: Removed session_uid set comparison, iterating only historical _tracked_objects\n\n")
        f.write("--- PHASE 1: MUTATED / LEGACY EXECUTION (EXPECTED FAILURE) ---\n")
        f.write(f"EXIT STATUS: {'FAILURE' if not mutated_res.wasSuccessful() else 'UNEXPECTED PASS'}\n")
        f.write(f"FAILURES COUNT: {len(mutated_res.failures)}\n")
        f.write(mutated_output)
        f.write("\n--- PHASE 2: PRODUCTION LOGIC RESTORED (EXPECTED PASS) ---\n")
        f.write(f"EXIT STATUS: {'PASS' if prod_res.wasSuccessful() else 'FAIL'}\n")
        f.write(prod_output)

    print(f"Case C05 logged to {log_path}. Mutated failed: {not mutated_res.wasSuccessful()}, Prod passed: {prod_res.wasSuccessful()}")
    return (not mutated_res.wasSuccessful()) and prod_res.wasSuccessful()


def run_case_f01() -> bool:
    """Case F01: Old member collection mistakenly retained after object is unlinked."""
    log_path = os.path.join(EVIDENCE_DIR, "counter_factual_f01_member_retention_leak.log")
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)

    orig_check = BlenderMeshEnvironmentAdapter._check_scene_changed

    def buggy_check(self):
        target_objects = self._gather_target_objects()
        current_mesh_objects = [o for o in target_objects if o.type == "MESH" and o.data is not None]
        current_uids = {o.session_uid for o in current_mesh_objects}
        # Injected Mutation: Only detect NEW members, ignore unlinked/removed members
        if not current_uids.issubset(self._tracked_session_uids):
            return True
        for obj in current_mesh_objects:
            uid = obj.session_uid
            snap = self._object_snapshots.get(uid)
            if snap is None or self._matrices_differ(obj.matrix_world, snap.matrix_world):
                return True
        return False

    BlenderMeshEnvironmentAdapter._check_scene_changed = buggy_check

    suite = unittest.TestSuite()
    suite.addTest(TestMeshEnvironmentQuery("test_43_c05_1_collection_member_unlinked"))
    mutated_res = runner.run(suite)
    mutated_output = stream.getvalue()

    BlenderMeshEnvironmentAdapter._check_scene_changed = orig_check
    stream_prod = io.StringIO()
    runner_prod = unittest.TextTestRunner(stream=stream_prod, verbosity=2)
    suite_prod = unittest.TestSuite()
    suite_prod.addTest(TestMeshEnvironmentQuery("test_43_c05_1_collection_member_unlinked"))
    prod_res = runner_prod.run(suite_prod)
    prod_output = stream_prod.getvalue()

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("=== COUNTER-FACTUAL VERIFICATION LOG: DEFECT F01 (MEMBER RETENTION LEAK) ===\n")
        f.write("TARGET DEFECT: F01 (Old collection member mistakenly retained in cache when unlinked)\n")
        f.write("MUTATION: Injected buggy check that only checks issubset (ignoring unlinked members)\n\n")
        f.write("--- PHASE 1: MUTATED / LEGACY EXECUTION (EXPECTED FAILURE) ---\n")
        f.write(f"EXIT STATUS: {'FAILURE' if not mutated_res.wasSuccessful() else 'UNEXPECTED PASS'}\n")
        f.write(f"FAILURES COUNT: {len(mutated_res.failures)}\n")
        f.write(mutated_output)
        f.write("\n--- PHASE 2: PRODUCTION LOGIC RESTORED (EXPECTED PASS) ---\n")
        f.write(f"EXIT STATUS: {'PASS' if prod_res.wasSuccessful() else 'FAIL'}\n")
        f.write(prod_output)

    print(f"Case F01 logged to {log_path}. Mutated failed: {not mutated_res.wasSuccessful()}, Prod passed: {prod_res.wasSuccessful()}")
    return (not mutated_res.wasSuccessful()) and prod_res.wasSuccessful()


def run_case_f02() -> bool:
    """Case F02: Old code treats valid empty BVH as invalid, triggering repeated rebuilds across 100 queries."""
    log_path = os.path.join(EVIDENCE_DIR, "counter_factual_f02_empty_bvh_repeated_rebuild.log")
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)

    orig_refresh = BlenderMeshEnvironmentAdapter.refresh

    def buggy_refresh(self, force=False):
        # Injected Mutation: Old logic that treated self._bvh is None as invalid, causing rebuild on every query
        if force or self._dirty or self._bvh is None:
            self.rebuild()
            return
        if self._check_scene_changed():
            self.rebuild()

    BlenderMeshEnvironmentAdapter.refresh = buggy_refresh

    suite = unittest.TestSuite()
    suite.addTest(TestMeshEnvironmentQuery("test_45_c05_3_non_empty_to_empty_transition_and_reuse"))
    mutated_res = runner.run(suite)
    mutated_output = stream.getvalue()

    BlenderMeshEnvironmentAdapter.refresh = orig_refresh
    stream_prod = io.StringIO()
    runner_prod = unittest.TextTestRunner(stream=stream_prod, verbosity=2)
    suite_prod = unittest.TestSuite()
    suite_prod.addTest(TestMeshEnvironmentQuery("test_45_c05_3_non_empty_to_empty_transition_and_reuse"))
    prod_res = runner_prod.run(suite_prod)
    prod_output = stream_prod.getvalue()

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("=== COUNTER-FACTUAL VERIFICATION LOG: DEFECT F02 (EMPTY BVH REPEATED REBUILD LEAK) ===\n")
        f.write("TARGET DEFECT: F02 (Old code treating valid empty BVH as invalid and rebuilding on every query)\n")
        f.write("MUTATION: Restored legacy refresh condition `if force or self._dirty or self._bvh is None: self.rebuild()`\n\n")
        f.write("--- PHASE 1: MUTATED / LEGACY EXECUTION (EXPECTED FAILURE) ---\n")
        f.write(f"EXIT STATUS: {'FAILURE' if not mutated_res.wasSuccessful() else 'UNEXPECTED PASS'}\n")
        f.write(f"FAILURES COUNT: {len(mutated_res.failures)}\n")
        f.write(mutated_output)
        f.write("\n--- PHASE 2: PRODUCTION LOGIC RESTORED (EXPECTED PASS) ---\n")
        f.write(f"EXIT STATUS: {'PASS' if prod_res.wasSuccessful() else 'FAIL'}\n")
        f.write(prod_output)

    print(f"Case F02 logged to {log_path}. Mutated failed: {not mutated_res.wasSuccessful()}, Prod passed: {prod_res.wasSuccessful()}")
    return (not mutated_res.wasSuccessful()) and prod_res.wasSuccessful()


def run_case_f03() -> bool:
    """Case F03: Mid-flight exception leaves cache stuck in REBUILDING instead of FAILED."""
    log_path = os.path.join(EVIDENCE_DIR, "counter_factual_f03_exception_state_residual.log")
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)

    orig_rebuild = BlenderMeshEnvironmentAdapter.rebuild

    def buggy_rebuild(self):
        # Injected Mutation: Simulate pre-fix code where self._gather_target_objects was outside try/except
        self._cache_state = AdapterCacheState.REBUILDING
        # If _gather_target_objects raises, cache_state is stuck in REBUILDING!
        target_objects = self._gather_target_objects()
        orig_rebuild(self)

    BlenderMeshEnvironmentAdapter.rebuild = buggy_rebuild

    suite = unittest.TestSuite()
    suite.addTest(TestMeshEnvironmentQuery("test_47_c06_rebuild_exception_safety"))
    mutated_res = runner.run(suite)
    mutated_output = stream.getvalue()

    BlenderMeshEnvironmentAdapter.rebuild = orig_rebuild
    stream_prod = io.StringIO()
    runner_prod = unittest.TextTestRunner(stream=stream_prod, verbosity=2)
    suite_prod = unittest.TestSuite()
    suite_prod.addTest(TestMeshEnvironmentQuery("test_47_c06_rebuild_exception_safety"))
    prod_res = runner_prod.run(suite_prod)
    prod_output = stream_prod.getvalue()

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("=== COUNTER-FACTUAL VERIFICATION LOG: DEFECT F03 (EXCEPTION STATE RESIDUAL IN REBUILDING) ===\n")
        f.write("TARGET DEFECT: F03 (Rebuild mid-flight exception leaving cache stuck in REBUILDING state)\n")
        f.write("MUTATION: Placed _gather_target_objects call outside try/except block without FAILED rollback\n\n")
        f.write("--- PHASE 1: MUTATED / LEGACY EXECUTION (EXPECTED FAILURE) ---\n")
        f.write(f"EXIT STATUS: {'FAILURE' if not mutated_res.wasSuccessful() else 'UNEXPECTED PASS'}\n")
        f.write(f"FAILURES COUNT: {len(mutated_res.failures)}\n")
        f.write(mutated_output)
        f.write("\n--- PHASE 2: PRODUCTION LOGIC RESTORED (EXPECTED PASS) ---\n")
        f.write(f"EXIT STATUS: {'PASS' if prod_res.wasSuccessful() else 'FAIL'}\n")
        f.write(prod_output)

    print(f"Case F03 logged to {log_path}. Mutated failed: {not mutated_res.wasSuccessful()}, Prod passed: {prod_res.wasSuccessful()}")
    return (not mutated_res.wasSuccessful()) and prod_res.wasSuccessful()


def main():
    print("Running Counter-Factual Verification Suite for Repair Unit 2 Final Closure...")
    c01_ok = run_case_c01()
    c03_ok = run_case_c03()
    c05_ok = run_case_c05()
    f01_ok = run_case_f01()
    f02_ok = run_case_f02()
    f03_ok = run_case_f03()

    all_passed = c01_ok and c03_ok and c05_ok and f01_ok and f02_ok and f03_ok
    if all_passed:
        print("\nALL COUNTER-FACTUAL EXPERIMENTS (C01, C03, C05, F01, F02, F03) VERIFIED SUCCESSFULLY (Mutated Failed, Prod Passed).")
        return 0
    else:
        print(f"\nCounter-factual verification failed: c01={c01_ok}, c03={c03_ok}, c05={c05_ok}, f01={f01_ok}, f02={f02_ok}, f03={f03_ok}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
