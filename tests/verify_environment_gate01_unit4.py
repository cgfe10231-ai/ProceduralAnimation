"""ProceduralAnimation — Environment Gate 01 / Repair Unit 4 Verification Script.

Executes standalone verification of Real Mesh Contact Elevation and Geometric Consistency:
- Reads `output/dynamics_playground_environment_gate01_u3_s2.blend` (or live scene).
- Verifies foot sole contact anchors against evaluated scene meshes via BlenderMeshEnvironmentAdapter.
- Audits normal compliance, air gaps, surface penetrations, and tangential drift.
- Confirms zero hardcoded Z=0.0m flattening across all elevated surfaces.
- Outputs verification metrics to `docs/evidence/environment_gate01_ru4/verification_report.json`.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import bpy
from mathutils import Vector

from src.motion.contact_model import (
    ContactRecord,
    ContactType,
    ContactLifecycle,
    DEFAULT_LIMB_LOCAL_ANCHORS,
)
from src.scene.blender_mesh_query_adapter import BlenderMeshEnvironmentAdapter


def verify_unit4_contact_elevation(
    blend_path: str = "output/dynamics_playground_environment_gate01_u3_s2.blend",
    output_report_path: Optional[str] = "docs/evidence/environment_gate01_ru4/verification_report.json",
) -> Dict[str, Any]:
    """Run full geometric contact audit on the generated terrain animation blend file."""
    abs_blend = os.path.abspath(blend_path)
    if not os.path.exists(abs_blend):
        raise FileNotFoundError(f"Target blend file not found: {abs_blend}")

    bpy.ops.wm.open_mainfile(filepath=abs_blend)
    scene = bpy.context.scene
    arm_obj = bpy.data.objects.get("CharacterArmature")
    if arm_obj is None:
        raise RuntimeError("CharacterArmature not found in scene")

    adapter = BlenderMeshEnvironmentAdapter(scene=scene, collection_names=("Playground_Surfaces",))
    if adapter.is_empty:
        raise RuntimeError("Playground_Surfaces collection is empty")

    contact_key = "environment_gate01_u3_contacts" if "environment_gate01_u3_contacts" in scene else "task7a2_contact_state_records"
    if contact_key not in scene:
        raise RuntimeError(f"Missing '{contact_key}' in scene metadata")

    contact_records = json.loads(scene[contact_key])
    local_anchor = DEFAULT_LIMB_LOCAL_ANCHORS["foot_L"]

    total_frames = len(contact_records)
    audited_stance_frames = 0
    elevated_stance_frames = 0
    max_gap_m = 0.0
    max_penetration_m = 0.0
    max_slip_m = 0.0
    zero_flattening_detected = False
    violations: List[Dict[str, Any]] = []

    for rec in contact_records:
        frame = rec["frame"]
        scene.frame_set(frame)
        bpy.context.view_layer.update()

        for limb_id, c_data in rec.get("contacts", {}).items():
            if not c_data.get("is_locked", False):
                continue

            audited_stance_frames += 1
            bone_name = "foot.L" if limb_id == "foot_L" else "foot.R"
            pb = arm_obj.pose.bones.get(bone_name)
            if pb is None:
                continue

            foot_mat_world = arm_obj.matrix_world @ pb.matrix
            p_sole = foot_mat_world @ Vector(local_anchor)

            q_res = adapter.ray_cast(
                origin=(p_sole.x, p_sole.y, 50.0),
                direction=(0.0, 0.0, -1.0),
                distance=100.0,
            )
            if not q_res.success:
                violations.append({
                    "frame": frame,
                    "limb": limb_id,
                    "reason": f"No ground support mesh hit: {q_res.error_reason}",
                })
                continue

            mesh_z = q_res.contact_point_world[2]
            if mesh_z > 0.10:
                elevated_stance_frames += 1

            contact_target_z = c_data.get("contact_xyz", [0, 0, 0])[2]
            # Verify no false flattening to 0.0m on elevated surfaces
            if mesh_z > 0.50 and abs(contact_target_z) < 0.01:
                zero_flattening_detected = True
                violations.append({
                    "frame": frame,
                    "limb": limb_id,
                    "reason": f"Zero flattening detected on elevated surface (mesh Z={mesh_z:.3f}m, contact Z={contact_target_z:.3f}m)",
                })

            crec = ContactRecord(
                contact_id=f"audit_{limb_id}",
                limb=limb_id,
                surface_id=q_res.surface_id,
                world_position=q_res.contact_point_world,
                world_normal=q_res.surface_normal_world,
                body_local_anchor=local_anchor,
            )
            chk = crec.check_geometric_compliance((p_sole.x, p_sole.y, p_sole.z))
            max_gap_m = max(max_gap_m, chk.distance_normal_m)
            max_penetration_m = max(max_penetration_m, chk.penetration_depth_m)
            max_slip_m = max(max_slip_m, chk.tangential_slip_m)

            if not chk.is_valid:
                violations.append({
                    "frame": frame,
                    "limb": limb_id,
                    "reason": chk.violation_reason,
                    "gap_mm": round(chk.distance_normal_m * 1000.0, 2),
                    "pen_mm": round(chk.penetration_depth_m * 1000.0, 2),
                    "slip_mm": round(chk.tangential_slip_m * 1000.0, 2),
                })

    status = "PASS" if (len(violations) == 0 and not zero_flattening_detected) else "FAIL"

    report = {
        "status": status,
        "blend_path": blend_path,
        "total_frames": total_frames,
        "audited_stance_frames": audited_stance_frames,
        "elevated_stance_frames": elevated_stance_frames,
        "max_air_gap_mm": round(max_gap_m * 1000.0, 2),
        "max_penetration_mm": round(max_penetration_m * 1000.0, 2),
        "max_tangential_slip_mm": round(max_slip_m * 1000.0, 2),
        "zero_flattening_detected": zero_flattening_detected,
        "total_violations": len(violations),
        "violations_sample": violations[:10],
    }

    if output_report_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_report_path)), exist_ok=True)
        with open(output_report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Environment Gate 01 / Unit 4 Contact Elevation")
    parser.add_argument("--blend", default="output/dynamics_playground_environment_gate01_u3_s2.blend")
    parser.add_argument("--report", default="docs/evidence/environment_gate01_ru4/verification_report.json")
    
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    args = parser.parse_args(argv)

    print(f"[UNIT4_VERIFY] Opening scene: {args.blend}")
    report = verify_unit4_contact_elevation(args.blend, args.report)
    print(f"[UNIT4_VERIFY] Status: {report['status']}")
    print(f"  Audited Stance Frames:  {report['audited_stance_frames']}")
    print(f"  Elevated Stance Frames: {report['elevated_stance_frames']}")
    print(f"  Max Air Gap:            {report['max_air_gap_mm']} mm (tol <= 15.0 mm)")
    print(f"  Max Penetration:        {report['max_penetration_mm']} mm (tol <= 10.0 mm)")
    print(f"  Max Tangential Slip:    {report['max_tangential_slip_mm']} mm (tol <= 20.0 mm)")
    print(f"  Zero Flattening Defect: {'DETECTED' if report['zero_flattening_detected'] else 'ZERO (Clean)'}")
    print(f"  Total Violations:       {report['total_violations']}")

    if report["status"] != "PASS":
        print(f"[UNIT4_VERIFY] FAILED with {report['total_violations']} violations:")
        for v in report["violations_sample"]:
            print(f"  - Frame {v.get('frame')}: {v.get('reason')}")
        return 1

    print("[UNIT4_VERIFY] SUCCESS: All contact elevations and geometric constraints 100% compliant.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
