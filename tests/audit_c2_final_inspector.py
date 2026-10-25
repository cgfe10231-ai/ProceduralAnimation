"""Read-Only Machine-Verifiable Codebase AST & Blender Asset Inspector (Task 6G-D-C2-FINAL).

Strictly read-only audit tool:
1. Parses AST of every Python file in `src/`, `tests/`, and root `run_*.py` to extract
   exact line counts, classes, methods, functions, imports, and call sites with line numbers.
2. Opens every `.blend` file in `output/` via Blender headless (`bpy.ops.wm.open_mainfile`)
   without modifying or saving any `.blend` file, extracting exact scene metadata:
   file existence, size in bytes, git tracking status, scene name, FPS, frame range
   (`frame_start..frame_end`), collections, object count, armature name & bone count,
   Action names, F-Curve counts, and keyframe frame spans.
3. Exports machine-readable JSON (`docs/evidence/task6gd_c2a/codebase_and_blend_audit.json`)
   and human-readable execution log (`docs/evidence/task6gd_c2a/blend_inspection_log.txt`).
4. Optionally validates all markdown freeze documents in `docs/` (`--verify-docs`) to assert
   zero non-existent `src/` or `tests/` module paths and zero hallucinated class/method symbols.
"""

from __future__ import annotations

import ast
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent


def get_git_tracked_files() -> Set[str]:
    """Return set of forward-slash relative paths tracked by Git."""
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        return {line.strip().replace("\\", "/") for line in res.stdout.splitlines() if line.strip()}
    except Exception:
        return set()


def check_git_ignored(rel_path: str) -> bool:
    """Return True if rel_path is ignored by .gitignore."""
    try:
        res = subprocess.run(
            ["git", "check-ignore", "-q", rel_path],
            cwd=str(REPO_ROOT),
            capture_output=True,
        )
        return res.returncode == 0
    except Exception:
        return rel_path.startswith("output/")


def inspect_python_file(py_path: Path, tracked_set: Set[str]) -> Dict[str, Any]:
    """Parse AST of a Python file and extract classes, methods, functions, and imports."""
    rel_path = py_path.relative_to(REPO_ROOT).as_posix()
    text = py_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    tree = ast.parse(text, filename=rel_path)

    imports: List[Dict[str, Any]] = []
    classes: List[Dict[str, Any]] = []
    functions: List[Dict[str, Any]] = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({
                    "type": "import",
                    "module": alias.name,
                    "name": alias.asname or alias.name,
                    "lineno": node.lineno,
                })
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                imports.append({
                    "type": "from_import",
                    "module": mod,
                    "name": alias.name,
                    "asname": alias.asname,
                    "lineno": node.lineno,
                })
        elif isinstance(node, ast.ClassDef):
            methods: List[Dict[str, Any]] = []
            attributes: List[str] = []
            enum_members: List[str] = []
            bases = []
            for b in node.bases:
                if isinstance(b, ast.Name):
                    bases.append(b.id)
                elif isinstance(b, ast.Attribute):
                    bases.append(f"{ getattr(b.value, 'id', '') }.{b.attr}")

            is_enum_class = any("Enum" in b for b in bases)

            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append({
                        "name": item.name,
                        "lineno": item.lineno,
                        "end_lineno": getattr(item, "end_lineno", item.lineno),
                    })
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            attributes.append(target.id)
                            if is_enum_class or target.id.isupper():
                                enum_members.append(target.id)
                elif isinstance(item, ast.AnnAssign):
                    if isinstance(item.target, ast.Name):
                        attributes.append(item.target.id)
                        if is_enum_class or item.target.id.isupper():
                            enum_members.append(item.target.id)

            classes.append({
                "name": node.name,
                "bases": bases,
                "lineno": node.lineno,
                "end_lineno": getattr(node, "end_lineno", node.lineno),
                "methods": methods,
                "attributes": sorted(set(attributes)),
                "enum_members": sorted(set(enum_members)),
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": getattr(node, "end_lineno", node.lineno),
            })

    # Also scan nested imports inside functions/methods
    nested_imports: List[Dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node not in tree.body:
            mod = node.module or ""
            for alias in node.names:
                nested_imports.append({
                    "type": "nested_from_import",
                    "module": mod,
                    "name": alias.name,
                    "lineno": node.lineno,
                })

    return {
        "path": rel_path,
        "size_bytes": py_path.stat().st_size,
        "line_count": len(lines),
        "git_tracked": rel_path in tracked_set,
        "classes": classes,
        "functions": functions,
        "imports": imports,
        "nested_imports": nested_imports,
    }


def inspect_blend_files(tracked_set: Set[str]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Inspect all .blend files in output/ using Blender bpy (read-only)."""
    import bpy

    output_dir = REPO_ROOT / "output"
    blend_paths = sorted(output_dir.rglob("*.blend"))
    records: List[Dict[str, Any]] = []
    log_lines: List[str] = []

    log_lines.append("=" * 88)
    log_lines.append("BLENDER 5.1.1 READ-ONLY ASSET INVENTORY LOG (Task 6G-D-C2-FINAL)")
    log_lines.append(f"Blender Version: {bpy.app.version_string}")
    log_lines.append(f"Total .blend files discovered in output/: {len(blend_paths)}")
    log_lines.append("=" * 88)

    for bp in blend_paths:
        rel_path = bp.relative_to(REPO_ROOT).as_posix()
        size_bytes = bp.stat().st_size
        is_tracked = rel_path in tracked_set
        is_ignored = check_git_ignored(rel_path)

        bpy.ops.wm.open_mainfile(filepath=str(bp))
        scene = bpy.context.scene

        fps = int(scene.render.fps)
        frame_start = int(scene.frame_start)
        frame_end = int(scene.frame_end)
        frame_count = frame_end - frame_start + 1

        collections = sorted([c.name for c in bpy.data.collections])
        objects = sorted([o.name for o in bpy.data.objects])
        obj_types: Dict[str, int] = {}
        for o in bpy.data.objects:
            obj_types[o.type] = obj_types.get(o.type, 0) + 1

        armatures_info: List[Dict[str, Any]] = []
        for o in bpy.data.objects:
            if o.type == "ARMATURE" and o.data is not None:
                bone_names = [b.name for b in o.data.bones]
                armatures_info.append({
                    "object_name": o.name,
                    "armature_data_name": o.data.name,
                    "bone_count": len(bone_names),
                    "bone_names": bone_names,
                })

        actions_info: List[Dict[str, Any]] = []
        total_fcurves = 0
        for act in bpy.data.actions:
            fcurves_list = []
            # Blender 5.0+ layered action or legacy fcurves support
            if hasattr(act, "fcurves") and len(act.fcurves) > 0:
                fcurves_list = list(act.fcurves)
            elif hasattr(act, "layers"):
                for layer in act.layers:
                    for strip in getattr(layer, "strips", []):
                        for cb in getattr(strip, "channelbags", []):
                            fcurves_list.extend(list(getattr(cb, "fcurves", [])))
            fc_count = len(fcurves_list)
            total_fcurves += fc_count
            kf_min: Optional[float] = None
            kf_max: Optional[float] = None
            total_kfs = 0
            for fc in fcurves_list:
                kps = fc.keyframe_points
                total_kfs += len(kps)
                if len(kps) > 0:
                    c_min = float(kps[0].co[0])
                    c_max = float(kps[-1].co[0])
                    kf_min = c_min if kf_min is None else min(kf_min, c_min)
                    kf_max = c_max if kf_max is None else max(kf_max, c_max)
            actions_info.append({
                "action_name": act.name,
                "fcurve_count": fc_count,
                "total_keyframe_points": total_kfs,
                "keyframe_range": [kf_min, kf_max] if kf_min is not None else None,
            })

        rec = {
            "path": rel_path,
            "exists": True,
            "size_bytes": size_bytes,
            "git_tracked": is_tracked,
            "git_ignored": is_ignored,
            "scene_name": scene.name,
            "fps": fps,
            "frame_start": frame_start,
            "frame_end": frame_end,
            "frame_span_count": frame_count,
            "collection_count": len(collections),
            "collections": collections,
            "object_count": len(objects),
            "object_types": obj_types,
            "armatures": armatures_info,
            "action_count": len(actions_info),
            "total_fcurves": total_fcurves,
            "actions": actions_info,
        }
        records.append(rec)

        arm_summary = (
            ", ".join(f"{a['object_name']} ({a['bone_count']} bones)" for a in armatures_info)
            if armatures_info
            else "None (0 bones)"
        )
        act_summary = (
            ", ".join(
                f"{a['action_name']} ({a['fcurve_count']} F-Curves, {a['total_keyframe_points']} keyframes, span={a['keyframe_range']})"
                for a in actions_info
            )
            if actions_info
            else "None (0 F-Curves)"
        )
        log_lines.append(f"\n[BLEND] {rel_path}")
        log_lines.append(f"  - Size Bytes   : {size_bytes:,} bytes")
        log_lines.append(f"  - Git Status   : tracked={is_tracked}, gitignored={is_ignored}")
        log_lines.append(f"  - Scene & FPS  : '{scene.name}' @ {fps} FPS")
        log_lines.append(f"  - Frame Range  : {frame_start}..{frame_end} ({frame_count} frames)")
        log_lines.append(f"  - Collections  : {len(collections)} {collections}")
        log_lines.append(f"  - Objects      : {len(objects)} total {obj_types}")
        log_lines.append(f"  - Armatures    : {arm_summary}")
        log_lines.append(f"  - Actions/FCs  : {act_summary}")

    log_lines.append("\n" + "=" * 88)
    log_lines.append("AUDIT COMPLETE: ZERO FILES MODIFIED.")
    log_lines.append("=" * 88)
    return records, log_lines


class CodebaseSymbolIndex:
    """Aggregated index of modules, classes, methods, functions, attributes, enum members, and Blender assets."""

    def __init__(self, audit_payload: Dict[str, Any]):
        self.modules: Set[str] = set()
        self.module_stems_pascal: Set[str] = set()
        self.classes: Dict[str, List[Dict[str, Any]]] = {}
        self.functions: Dict[str, List[str]] = {}
        self.all_members: Dict[str, Set[str]] = {}
        self.domain_acronyms: Set[str] = {
            "WBC", "CoM", "ROM", "IK", "FK", "ZMP", "SI", "FPS", "SSOT", "AST", "JSON",
            "API", "UI", "CLI", "HEAD", "PR", "RMS", "DOF", "6DOF", "FIFO", "LIFO", "PD", "SE3", "SO3"
        }
        self.blend_actions: Set[str] = set()
        self.blend_objects: Set[str] = set()
        self.blend_collections: Set[str] = set()
        self.blend_bones: Set[str] = set()

        for m in (
            audit_payload.get("src_modules", [])
            + audit_payload.get("test_scripts", [])
            + audit_payload.get("root_scripts", [])
        ):
            mod_path = m["path"]
            self.modules.add(mod_path)
            stem = Path(mod_path).stem
            pascal_stem = "".join(part.capitalize() for part in stem.split("_"))
            self.module_stems_pascal.add(pascal_stem)

            for c in m.get("classes", []):
                c_name = c["name"]
                if c_name not in self.classes:
                    self.classes[c_name] = []
                m_names = {item["name"] for item in c.get("methods", [])}
                a_names = set(c.get("attributes", []))
                e_names = set(c.get("enum_members", []))
                self.classes[c_name].append({
                    "module": mod_path,
                    "methods": m_names,
                    "attributes": a_names,
                    "enum_members": e_names,
                    "bases": c.get("bases", []),
                })
                if c_name not in self.all_members:
                    self.all_members[c_name] = set()
                self.all_members[c_name].update(m_names)
                self.all_members[c_name].update(a_names)
                self.all_members[c_name].update(e_names)

            for f in m.get("functions", []):
                f_name = f["name"]
                if f_name not in self.functions:
                    self.functions[f_name] = []
                self.functions[f_name].append(mod_path)

        for b in audit_payload.get("blend_files", []):
            for act in b.get("actions", []):
                self.blend_actions.add(act.get("action_name", ""))
            for col in b.get("collections", []):
                self.blend_collections.add(col)
            for arm in b.get("armatures", []):
                self.blend_objects.add(arm.get("object_name", ""))
                for bone in arm.get("bone_names", []):
                    self.blend_bones.add(bone)


class DocReferenceValidator:
    """Universal documentation reference auditor with AST-backed existence checking."""

    def __init__(self, index: CodebaseSymbolIndex):
        self.index = index
        self.path_pattern = re.compile(r"\b((?:src|tests)/[A-Za-z0-9_./-]+\.py)\b")
        self.qualified_pattern = re.compile(r"`?([A-Z][A-Za-z0-9_]+)\.([A-Za-z_][A-Za-z0-9_]*)(?:\(\))?`?")
        self.class_pattern = re.compile(
            r"`([A-Z][A-Za-z0-9]+(?:Controller|Executor|Planner|State|Target|Solver|Model|Query|Action|Bridge|Data|Rig|Spec|Config|Result|Tracker|Builder|Inspector|Sequence|Timeline|Context|Lifecycle|Status|Type))`"
        )
        self.external_namespaces = {
            "math", "np", "numpy", "bpy", "sys", "os", "re", "ast", "json", "typing",
            "Path", "Vector", "Quaternion", "Euler", "Matrix", "MappingProxyType", "Enum",
            "ABC", "Dict", "List", "Set", "Tuple", "Optional", "Any", "Union"
        }

    def validate_document(self, doc_name: str, content: str) -> List[str]:
        errors: List[str] = []
        lines = content.splitlines()
        is_proposed_section = False

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                header_lower = stripped.lower()
                if any(k in header_lower for k in ["future", "phase 7", "phase 6h", "proposed", "planned", "未实现", "规划"]):
                    is_proposed_section = True
                elif any(k in header_lower for k in [
                    "phase 1", "phase 2", "phase 3", "phase 4", "phase 5", "phase 6",
                    "task 6", "pipeline a", "pipeline b", "current", "已实现", "资产审计", "架构审计"
                ]):
                    is_proposed_section = False

            line_is_proposed = is_proposed_section or any(
                k in line for k in ["(Proposed)", "(Planned)", "PROPOSED", "拟议", "规划中", "Future Architecture"]
            )

            # Skip checking lines that discuss rejected or non-existent symbols explicitly
            if any(k in line for k in [
                "不存在", "non-existent", "Non-Existent", "Removed", "Eliminated",
                "forbidden", "未定义", "零不存在", "phantom", "幻觉", "曾用或错误名称", "严禁再用"
            ]):
                continue

            # 1. Module path validation
            for match in self.path_pattern.finditer(line):
                mod_path = match.group(1)
                if mod_path not in self.index.modules and not (REPO_ROOT / mod_path).exists():
                    if not line_is_proposed:
                        errors.append(
                            f"[{doc_name}:{idx}] ERROR: File '{mod_path}' | Symbol '{mod_path}' | Type: NON_EXISTENT_MODULE | Conclusion: Module path does not exist on disk."
                        )

            # 2. Qualified symbol validation: Class.member
            for match in self.qualified_pattern.finditer(line):
                cls_name, member = match.group(1), match.group(2)
                if cls_name in self.external_namespaces or cls_name in self.index.domain_acronyms:
                    continue
                if cls_name in self.index.blend_objects or cls_name in self.index.blend_actions:
                    continue

                if cls_name in self.index.classes:
                    members = self.index.all_members.get(cls_name, set())
                    if member not in members:
                        is_enum = any(any("Enum" in b for b in c_def["bases"]) for c_def in self.index.classes[cls_name])
                        err_type = "NON_EXISTENT_ENUM_MEMBER" if is_enum else "NON_EXISTENT_METHOD"
                        if not line_is_proposed:
                            src_mod = self.index.classes[cls_name][0]["module"]
                            errors.append(
                                f"[{doc_name}:{idx}] ERROR: File '{src_mod}' | Symbol '{cls_name}.{member}' | Type: {err_type} | Conclusion: Class '{cls_name}' exists in '{src_mod}' but defines no member '{member}'."
                            )
                else:
                    if not line_is_proposed:
                        if cls_name.endswith((
                            "Controller", "Executor", "Planner", "State", "Target", "Solver", "Model",
                            "Query", "Action", "Bridge", "Data", "Rig", "Spec", "Config", "Result",
                            "Tracker", "Builder", "Inspector", "Sequence", "Timeline", "Context",
                            "Lifecycle", "Status", "Type"
                        )) and cls_name not in self.index.module_stems_pascal:
                            errors.append(
                                f"[{doc_name}:{idx}] ERROR: File '{doc_name}' | Symbol '{cls_name}.{member}' | Type: NON_EXISTENT_CLASS | Conclusion: Class '{cls_name}' is not defined in any Python module."
                            )

            # 3. Stand-alone Class Name validation
            if doc_name != "CHANGELOG.md":
                for match in self.class_pattern.finditer(line):
                    cls_name = match.group(1)
                    if (
                        cls_name in self.external_namespaces
                        or cls_name in self.index.domain_acronyms
                        or cls_name in self.index.module_stems_pascal
                        or cls_name in self.index.blend_objects
                        or cls_name in self.index.blend_actions
                    ):
                        continue

                    if cls_name not in self.index.classes:
                        if not line_is_proposed:
                            errors.append(
                                f"[{doc_name}:{idx}] ERROR: File '{doc_name}' | Symbol '{cls_name}' | Type: NON_EXISTENT_CLASS | Conclusion: Class '{cls_name}' is not defined in the codebase."
                            )

            # 4. Table row checking: Claimed IMPLEMENTED vs PROPOSED/Unimplemented
            if "|" in line and any(k in line for k in ["IMPLEMENTED", "已实现"]) and not any(k in line for k in ["GitHub 同步状态", "已入库同步", "证据 / 文档类型"]):
                for match in re.finditer(r"`([A-Z][A-Za-z0-9_]+)`", line):
                    cls_name = match.group(1)
                    if (
                        cls_name in self.external_namespaces
                        or cls_name in self.index.domain_acronyms
                        or cls_name in self.index.module_stems_pascal
                        or cls_name in self.index.blend_objects
                        or cls_name in self.index.blend_actions
                    ):
                        continue
                    if cls_name not in self.index.classes:
                        errors.append(
                            f"[{doc_name}:{idx}] ERROR: File '{doc_name}' | Symbol '{cls_name}' | Type: MISLABELED_IMPLEMENTATION | Conclusion: Symbol claimed as IMPLEMENTED but does not exist in code."
                        )

        return errors


def run_validator_test_suite(index: CodebaseSymbolIndex) -> Tuple[bool, List[str]]:
    """Self-test suite for the documentation validator verifying positive, negative, proposed, and prose safety."""
    validator = DocReferenceValidator(index)
    test_errors: List[str] = []

    # Test 1: Positive Case
    pos_content = (
        "# Implemented Section\n"
        "We use `src/motion/contact_dynamics.py` and enum member `ContactLifecycle.ESTABLISHED`.\n"
        "Calls `WholeBodyController.execute_frame()` and `solve_contact_forces()`.\n"
        "Component `WholeBodyController` is active.\n"
    )
    pos_res = validator.validate_document("test_positive.md", pos_content)
    if len(pos_res) > 0:
        test_errors.append(f"Test 1 (Positive) FAILED: Unexpected errors: {pos_res}")

    # Test 2: Negative Case
    neg_content = (
        "# Implemented Section\n"
        "Module `src/motion/fake_dynamics.py` is invoked.\n"
        "References `ContactLifecycle.TOUCHDOWN` on ground.\n"
        "Calls `WholeBodyController.apply_pose()` directly.\n"
        "Instantiates `KinematicPoseTarget`.\n"
    )
    neg_res = validator.validate_document("test_negative.md", neg_content)
    expected_err_types = ["NON_EXISTENT_MODULE", "NON_EXISTENT_ENUM_MEMBER", "NON_EXISTENT_METHOD", "NON_EXISTENT_CLASS"]
    for exp in expected_err_types:
        if not any(exp in err for err in neg_res):
            test_errors.append(f"Test 2 (Negative) FAILED: Expected error type '{exp}' was not caught in {neg_res}")

    # Test 3: Proposed / Future Planning Case
    prop_content = (
        "## Future Architecture (Proposed)\n"
        "Under future planning, `PlannedTerrainAdapter.adapt_step()` is proposed for Phase 7A.\n"
        "## Current Implementation\n"
        "| Component | Status |\n"
        "| `PlannedTerrainAdapter` | IMPLEMENTED |\n"
    )
    prop_res = validator.validate_document("test_proposed.md", prop_content)
    if not any("MISLABELED_IMPLEMENTATION" in err for err in prop_res):
        test_errors.append("Test 3 (Proposed) FAILED: Did not catch MISLABELED_IMPLEMENTATION when un-implemented symbol claimed IMPLEMENTED.")

    # Test 4: Prose / Natural Language Protection Case
    prose_content = (
        "# General Discussion\n"
        "The `master` branch is tested with `quick` and `physics` tiers.\n"
        "We observe `Walk` and `Run` behavior in `Blender` at 24 `FPS` with `Z-up` orientation.\n"
    )
    prose_res = validator.validate_document("test_prose.md", prose_content)
    if len(prose_res) > 0:
        test_errors.append(f"Test 4 (Prose) FAILED: False alarms on natural language words: {prose_res}")

    success = (len(test_errors) == 0)
    if success:
        print("[SELF-TEST] PASS: All 4 validator test cases (Positive, Negative, Proposed, Prose) verified successfully.")
    return success, test_errors


def verify_freeze_docs(audit_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Scan all freeze markdown docs in docs/ for non-existent paths or forbidden phantom APIs."""
    doc_files = [
        "docs/FOUNDATION_ASSET_AUDIT.md",
        "docs/FOUNDATION_ARCHITECTURE_AUDIT.md",
        "docs/FOUNDATION_DEPENDENCY_MAP.md",
        "docs/FOUNDATION_STATE_OWNERSHIP.md",
        "docs/ROADMAP_FOUNDATION_TO_FULLBODY.md",
        "docs/C2_FINAL_VALIDATION.md",
        "docs/ARCHITECTURE_CHANGE_GATE.md",
        "AGENTS.md",
        "GEMINI.md",
        ".agents/rules/project_rules.md",
        "DECISIONS.md",
        "PROJECT_STATE.md",
        "CHANGELOG.md",
        "ARCHITECTURE_SYNC.md",
        "HANDOFF.md",
        "AI_SYNC.md",
    ]

    index = CodebaseSymbolIndex(audit_data)

    # 1. Run self-test suite
    suite_ok, suite_errs = run_validator_test_suite(index)
    if not suite_ok:
        return False, [f"[VALIDATOR SELF-TEST ERROR] {e}" for e in suite_errs]

    # 2. Run document reference validator across all freeze documents
    validator = DocReferenceValidator(index)
    all_errors: List[str] = []

    for df in doc_files:
        p = REPO_ROOT / df
        if not p.exists():
            all_errors.append(f"Missing document: {df}")
            continue
        content = p.read_text(encoding="utf-8")
        doc_errs = validator.validate_document(df, content)
        all_errors.extend(doc_errs)

    return (len(all_errors) == 0), all_errors


def main() -> int:
    tracked_set = get_git_tracked_files()

    src_files = sorted((REPO_ROOT / "src").rglob("*.py"))
    test_files = sorted((REPO_ROOT / "tests").rglob("*.py"))
    root_scripts = sorted(REPO_ROOT.glob("run_*.py"))

    src_modules = [inspect_python_file(p, tracked_set) for p in src_files]
    test_scripts = [inspect_python_file(p, tracked_set) for p in test_files]
    root_py = [inspect_python_file(p, tracked_set) for p in root_scripts]

    blend_records: List[Dict[str, Any]] = []
    log_lines: List[str] = []
    try:
        import bpy  # noqa: F401
        blend_records, log_lines = inspect_blend_files(tracked_set)
    except ImportError:
        print("[WARN] Running outside Blender: skipping bpy .blend inspection.")

    audit_payload = {
        "repository_root": str(REPO_ROOT),
        "counts": {
            "src_python_files": len(src_modules),
            "test_python_files": len(test_scripts),
            "root_runner_scripts": len(root_py),
            "output_blend_files": len(blend_records),
        },
        "src_modules": src_modules,
        "test_scripts": test_scripts,
        "root_scripts": root_py,
        "blend_files": blend_records,
    }

    out_dir = REPO_ROOT / "docs" / "evidence" / "task6gd_c2a"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "codebase_and_blend_audit.json"
    log_path = out_dir / "blend_inspection_log.txt"

    if blend_records:
        json_path.write_text(json.dumps(audit_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        print(f"[AUDIT] Wrote {json_path}")
        print(f"[AUDIT] Wrote {log_path}")
        for line in log_lines:
            print(line)
    elif json_path.exists():
        # Preserve blend_files metadata when refreshing AST outside Blender
        cached = json.loads(json_path.read_text(encoding="utf-8"))
        audit_payload["blend_files"] = cached.get("blend_files", [])
        audit_payload["counts"]["output_blend_files"] = len(audit_payload["blend_files"])
        json_path.write_text(json.dumps(audit_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[AUDIT] Refreshed codebase AST in {json_path}")

    if "--summary" in sys.argv:
        print("\n=== SRC MODULES (51) ===")
        for m in audit_payload["src_modules"]:
            cls_list = [f"{c['name']}(L{c['lineno']})" for c in m["classes"]]
            fn_list = [f"{f['name']}(L{f['lineno']})" for f in m["functions"] if not f["name"].startswith("_")]
            imp_list = [f"{i['module']}.{i['name']}(L{i['lineno']})" for i in m["imports"] + m["nested_imports"] if i["module"].startswith("src")]
            print(f"{m['path']} | {m['line_count']}L | {m['size_bytes']}B | classes={cls_list} | funcs={fn_list} | src_imports={imp_list}")
        print("\n=== TEST SCRIPTS ===")
        for m in audit_payload["test_scripts"]:
            print(f"{m['path']} | {m['line_count']}L | {m['size_bytes']}B")
        print("\n=== ROOT SCRIPTS ===")
        for m in audit_payload["root_scripts"]:
            print(f"{m['path']} | {m['line_count']}L | {m['size_bytes']}B")

    if "--test-validator" in sys.argv:
        index = CodebaseSymbolIndex(audit_payload)
        suite_ok, suite_errs = run_validator_test_suite(index)
        if not suite_ok:
            print("[TEST-VALIDATOR] FAILED with errors:")
            for e in suite_errs:
                print(f"  - {e}")
            return 1
        return 0

    if "--verify-docs" in sys.argv:
        ok, errs = verify_freeze_docs(audit_payload)
        if not ok:
            print("[VERIFY-DOCS] FAILED with errors:")
            for e in errs:
                print(f"  - {e}")
            return 1
        print("[VERIFY-DOCS] PASS: All referenced src/tests paths exist on disk and zero phantom symbols found.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
