import json
import os
import runpy
import sys
import traceback
from pathlib import Path
from dataclasses import fields
from typing import Optional, Tuple, get_type_hints

root = Path(os.environ["TASK10C_REPO_ROOT"])
sys.path.insert(0, str(root))

from src.motion.kinematic_bridge import (
    PlannedHandTarget,
    KinematicPlannedPose,
)
from src.motion.contact_model import ContactType

records = []
result_path = Path(os.environ["TASK10C_RESULT_JSON"])

def save_results():
    result_path.write_text(
        json.dumps(
            {
                "node": "10-c-child2",
                "source_head": "eeb1d740844210e7e2df321fab7638469c9f572a",
                "results": records,
                "passed": sum(x["status"] == "PASS" for x in records),
                "failed": sum(x["status"] != "PASS" for x in records),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

def check(name, fn):
    try:
        value = fn()
        if value is False:
            raise AssertionError("Test returned False")
    except Exception as exc:
        records.append({
            "test": name,
            "status": "FAIL",
            "error": repr(exc),
        })
        save_results()
        traceback.print_exc()
        raise
    records.append({"test": name, "status": "PASS"})
    save_results()
    print("PASS:", name, flush=True)

old_names = [
    "world_xyz",
    "rotation_deg",
    "enabled",
    "weight",
    "contact_intent",
    "is_locked",
    "surface_id",
    "contact_type",
    "normal_world",
]

def a01():
    names = [f.name for f in fields(PlannedHandTarget)]
    assert names == old_names + [
        "pole_hint_world_xyz",
        "clamp_reach",
    ], names
    hints = get_type_hints(PlannedHandTarget)
    assert hints["pole_hint_world_xyz"] == Optional[
        Tuple[float, float, float]
    ]
    assert hints["clamp_reach"] is bool

def a02():
    obj = PlannedHandTarget(
        world_xyz=(0.0, 0.0, 0.0),
        enabled=False,
        contact_intent=False,
    )
    assert obj.enabled is False
    assert obj.contact_intent is False
    assert obj.pole_hint_world_xyz is None
    assert obj.clamp_reach is True

def a03():
    original = (
        (1.0, 2.0, 3.0),
        None,
        True,
        0.75,
        True,
        False,
        "bar",
        ContactType.FREE,
        (0.0, 0.0, 1.0),
    )
    obj = PlannedHandTarget(*original)
    assert tuple(getattr(obj, name) for name in old_names) == original
    assert obj.pole_hint_world_xyz is None
    assert obj.clamp_reach is True

def a04():
    obj = PlannedHandTarget((0.0, 0.0, 0.0))
    assert obj.pole_hint_world_xyz is None
    assert obj.clamp_reach is True

def a05():
    point = (0.15, -0.25, 1.35)
    obj = PlannedHandTarget(
        (0.0, 0.0, 0.0),
        pole_hint_world_xyz=point,
    )
    assert obj.pole_hint_world_xyz == point

def a06():
    on = PlannedHandTarget(
        (0.0, 0.0, 0.0),
        clamp_reach=True,
    )
    off = PlannedHandTarget(
        (0.0, 0.0, 0.0),
        clamp_reach=False,
    )
    assert on.clamp_reach is True
    assert off.clamp_reach is False

def a07():
    left = PlannedHandTarget(
        (1.0, 2.0, 3.0),
        pole_hint_world_xyz=(0.1, 0.2, 0.3),
        clamp_reach=False,
    )
    right = PlannedHandTarget(
        (-1.0, 2.0, 3.0),
        pole_hint_world_xyz=(-0.1, 0.2, 0.3),
        clamp_reach=True,
    )
    pose = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, 0.0, 0.0),
        hand_L=left,
        hand_R=right,
    )
    assert pose.hand_L is left
    assert pose.hand_R is right
    assert left is not right
    assert left.clamp_reach is False
    assert right.clamp_reach is True
    left.pole_hint_world_xyz = (4.0, 5.0, 6.0)
    assert right.pole_hint_world_xyz == (-0.1, 0.2, 0.3)

check("A01_field_structure", a01)
check("A02_legacy_keyword_constructor", a02)
check("A03_legacy_positional_constructor", a03)
check("A04_field_defaults", a04)
check("A05_explicit_pole_hint", a05)
check("A06_explicit_clamp_reach", a06)
check("A07_left_right_instance_isolation", a07)

# B组：只执行现有Bridge测试中的指定三个函数
test_module = runpy.run_path(
    str(root / "tests" / "verify_task6gc_r3b1_bridge.py"),
    run_name="task10c_child2_selected_tests",
)

selected = [
    ("B01_bridge_lossless_mapping",
     "test_01_lossless_input_mapping"),
    ("B02_bridge_fk_ik_arbitration",
     "test_02_fk_ik_arbitration_and_ownership"),
    ("B03_bridge_hand_contact_decoupling",
     "test_11_hand_ik_vs_contact_intent_decoupling"),
]

for name, function_name in selected:
    check(name, test_module[function_name])

print("TASK10C_CHILD2_ALL_10_TESTS_PASS", flush=True)