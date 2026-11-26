import json
import math
import os
import runpy
import sys
import traceback

from pathlib import Path

import bpy

ROOT = Path(os.environ["TASK10C_REPO_ROOT"]).resolve()
RESULT = Path(os.environ["TASK10C_RESULT_JSON"]).resolve()

sys.path.insert(0, str(ROOT))

from src.motion.kinematic_bridge import (
    PlannedHandTarget,
    KinematicPlannedPose,
    convert_planned_pose_to_wbc_targets,
)

records = []

SOURCE_HEAD = (
    "8f640b0fdcee18de47250b3eaee0b9ee43a03304"
)

print("NODE=10-c-child3", flush=True)
print("SOURCE_HEAD=" + SOURCE_HEAD, flush=True)
print("BLENDER_VERSION=" + bpy.app.version_string, flush=True)


def save():
    RESULT.write_text(
        json.dumps(
            {
                "node": "10-c-child3",
                "source_head": SOURCE_HEAD,
                "blender_version": bpy.app.version_string,
                "results": records,
                "passed": sum(
                    r["status"] == "PASS" for r in records
                ),
                "failed": sum(
                    r["status"] != "PASS" for r in records
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def check(name, fn):
    try:
        fn()
    except Exception as exc:
        records.append({
            "test": name,
            "status": "FAIL",
            "error": repr(exc),
        })
        save()
        traceback.print_exc()
        raise

    records.append({
        "test": name,
        "status": "PASS",
    })
    save()
    print("PASS:", name, flush=True)


def make_hand(
    side,
    enabled=True,
    weight=1.0,
    pole=None,
    clamp=True,
    contact_intent=False,
):
    x = -0.25 if side == "L" else 0.25

    return PlannedHandTarget(
        world_xyz=(x, -7.6, 1.3),
        rotation_deg=(10.0, 5.0, -3.0),
        enabled=enabled,
        weight=weight,
        pole_hint_world_xyz=pole,
        clamp_reach=clamp,
        contact_intent=contact_intent,
    )


def make_pose(left=None, right=None, fk=None):
    return KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, -8.0, 0.0),
        hand_L=left,
        hand_R=right,
        fk_joint_rotations_deg=fk if fk is not None else {},
    )


def convert(left=None, right=None, fk=None):
    return convert_planned_pose_to_wbc_targets(
        make_pose(left, right, fk)
    )


# --------------------------------------------------
# C3-T01: Left Pole Hint
# --------------------------------------------------

def t01():
    left = make_hand(
        "L",
        weight=0.75,
        pole=(-0.4, -7.5, 1.1),
        clamp=False,
    )
    out = convert(left=left)

    assert out.hand_L.effector_id == "hand_L"
    assert out.hand_L.target_world_xyz == left.world_xyz
    assert out.hand_L.target_rotation_deg == left.rotation_deg
    assert out.hand_L.pole_hint_world_xyz == left.pole_hint_world_xyz
    assert out.hand_L.weight == 0.75
    assert out.hand_L.enabled is True


# --------------------------------------------------
# C3-T02: Right Pole Hint
# --------------------------------------------------

def t02():
    right = make_hand(
        "R",
        weight=0.6,
        pole=(0.4, -7.5, 1.1),
    )
    out = convert(right=right)

    assert out.hand_R.effector_id == "hand_R"
    assert out.hand_R.target_world_xyz == right.world_xyz
    assert out.hand_R.target_rotation_deg == right.rotation_deg
    assert out.hand_R.pole_hint_world_xyz == right.pole_hint_world_xyz
    assert out.hand_R.weight == 0.6
    assert out.hand_R.enabled is True


# --------------------------------------------------
# C3-T03: Left Clamp
# --------------------------------------------------

def t03():
    for value in (True, False):
        out = convert(
            left=make_hand("L", clamp=value)
        )
        assert out.hand_L.clamp_reach is value


# --------------------------------------------------
# C3-T04: Right Clamp
# --------------------------------------------------

def t04():
    for value in (True, False):
        out = convert(
            right=make_hand("R", clamp=value)
        )
        assert out.hand_R.clamp_reach is value


# --------------------------------------------------
# C3-T05: Left IK / Right FK
# --------------------------------------------------

def t05():
    out = convert(
        left=make_hand("L", enabled=True),
        right=make_hand("R", enabled=False),
    )

    assert out.hand_L.enabled is True
    assert out.hand_L.weight == 1.0
    assert out.hand_R.enabled is False
    assert out.hand_R.weight == 0.0


# --------------------------------------------------
# C3-T06: Left FK / Right IK
# --------------------------------------------------

def t06():
    out = convert(
        left=make_hand("L", enabled=False),
        right=make_hand("R", enabled=True),
    )

    assert out.hand_L.enabled is False
    assert out.hand_L.weight == 0.0
    assert out.hand_R.enabled is True
    assert out.hand_R.weight == 1.0


# --------------------------------------------------
# C3-T07: Both Hands Independent
# --------------------------------------------------

def t07():
    left = make_hand(
        "L",
        weight=0.25,
        pole=(-0.3, -7.4, 1.2),
        clamp=False,
    )
    right = make_hand(
        "R",
        weight=0.85,
        pole=(0.4, -7.3, 1.4),
        clamp=True,
    )

    out = convert(left=left, right=right)

    assert out.hand_L is not out.hand_R
    assert out.hand_L.target_world_xyz == left.world_xyz
    assert out.hand_R.target_world_xyz == right.world_xyz
    assert out.hand_L.pole_hint_world_xyz == left.pole_hint_world_xyz
    assert out.hand_R.pole_hint_world_xyz == right.pole_hint_world_xyz
    assert out.hand_L.clamp_reach is False
    assert out.hand_R.clamp_reach is True
    assert out.hand_L.weight == 0.25
    assert out.hand_R.weight == 0.85


# --------------------------------------------------
# C3-T08: Zero Weight Is Valid
# --------------------------------------------------

def t08():
    left = make_hand(
        "L",
        enabled=True,
        weight=0.0,
        contact_intent=True,
    )

    out = convert(left=left)

    assert out.hand_L.enabled is True
    assert out.hand_L.weight == 0.0
    assert left.contact_intent is True


# --------------------------------------------------
# C3-T09: Invalid Weight Rejection
# --------------------------------------------------

def expect_error(side, weight, expected_type):
    left = make_hand("L") if side == "R" else None
    right = make_hand("R") if side == "L" else None

    invalid = make_hand(
        side,
        enabled=True,
        weight=weight,
    )

    if side == "L":
        left = invalid
    else:
        right = invalid

    try:
        convert(left=left, right=right)
    except expected_type as exc:
        assert f"hand_{side}.weight" in str(exc)
    except Exception as exc:
        raise AssertionError(
            f"Unexpected exception for hand_{side}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    else:
        raise AssertionError(
            f"Invalid weight was accepted: hand_{side}"
        )


def t09():
    invalid_values = [
        (float("nan"), ValueError),
        (float("inf"), ValueError),
        (-float("inf"), ValueError),
        (-0.1, ValueError),
        (1.1, ValueError),
        (10**400, ValueError),
        (-(10**400), ValueError),
        ("0.5", TypeError),
        (None, TypeError),
        (True, TypeError),
        (False, TypeError),
    ]

    for side in ("L", "R"):
        for value, expected in invalid_values:
            expect_error(side, value, expected)

    for side in ("L", "R"):
        for value in (0, 1, 0.5):
            target = make_hand(side, weight=value)
            if side == "L":
                out = convert(left=target)
                actual = out.hand_L.weight
            else:
                out = convert(right=target)
                actual = out.hand_R.weight

            assert actual == value


# --------------------------------------------------
# C3-T10: Failed Conversion Must Not Write Scene
# --------------------------------------------------

def scene_snapshot():
    objects = tuple(
        sorted(
            (
                obj.name,
                tuple(obj.location),
                tuple(obj.rotation_euler),
                tuple(obj.scale),
            )
            for obj in bpy.data.objects
        )
    )

    return (
        objects,
        len(bpy.data.meshes),
        len(bpy.data.armatures),
        len(bpy.data.actions),
        bpy.context.scene.frame_current,
    )


def t10():
    for side in ("L", "R"):
        before = scene_snapshot()

        expect_error(
            side,
            float("nan"),
            ValueError,
        )

        after = scene_snapshot()

        assert before == after, (
            f"Blender scene changed after invalid hand_{side} weight"
        )


# --------------------------------------------------
# C3-T11: Preserve FK Mapping
# --------------------------------------------------

def t11():
    fk = {
        "upper_arm.L": (15.0, 0.0, -5.0),
        "forearm.L": (0.0, 25.0, 0.0),
        "upper_arm.R": (-12.0, 0.0, 4.0),
    }

    planned = make_pose(
        left=make_hand("L", enabled=False),
        right=make_hand("R", enabled=False),
        fk=fk,
    )

    out = convert_planned_pose_to_wbc_targets(planned)

    assert out.fk_joint_rotations_deg == fk
    assert out.fk_joint_rotations_deg is not fk
    assert out.root_position == planned.root_position
    assert out.foot_L.target_world_xyz == planned.foot_L.world_xyz
    assert out.foot_R.target_world_xyz == planned.foot_R.world_xyz


# --------------------------------------------------
# C3-T12: IK and Contact Intent Decoupling
# --------------------------------------------------

def t12():
    reaching = make_hand(
        "L",
        enabled=True,
        weight=1.0,
        contact_intent=False,
    )

    approaching = make_hand(
        "L",
        enabled=True,
        weight=0.0,
        contact_intent=True,
    )

    out_reach = convert(left=reaching)
    out_approach = convert(left=approaching)

    assert out_reach.hand_L.enabled is True
    assert out_reach.hand_L.weight == 1.0
    assert reaching.contact_intent is False

    assert out_approach.hand_L.enabled is True
    assert out_approach.hand_L.weight == 0.0
    assert approaching.contact_intent is True


# --------------------------------------------------
# Run 12 New Contract Tests
# --------------------------------------------------

new_tests = [
    ("C3-T01", t01),
    ("C3-T02", t02),
    ("C3-T03", t03),
    ("C3-T04", t04),
    ("C3-T05", t05),
    ("C3-T06", t06),
    ("C3-T07", t07),
    ("C3-T08", t08),
    ("C3-T09", t09),
    ("C3-T10", t10),
    ("C3-T11", t11),
    ("C3-T12", t12),
]

for name, fn in new_tests:
    check(name, fn)


# --------------------------------------------------
# Historical Bridge Tests
# --------------------------------------------------

historical = runpy.run_path(
    str(ROOT / "tests" / "verify_task6gc_r3b1_bridge.py"),
    run_name="task10c_child3_selected_tests",
)

old_tests = [
    (
        "C3-T13",
        "test_01_lossless_input_mapping",
    ),
    (
        "C3-T14",
        "test_02_fk_ik_arbitration_and_ownership",
    ),
    (
        "C3-T15",
        "test_11_hand_ik_vs_contact_intent_decoupling",
    ),
]

for name, function_name in old_tests:
    def run_historical(fn=historical[function_name]):
        assert fn() is True

    check(name, run_historical)


assert len(records) == 15
assert all(r["status"] == "PASS" for r in records)

print(
    "TASK10C_CHILD3_ALL_15_TESTS_PASS",
    flush=True,
)