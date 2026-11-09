"""CONTRACT-10 Verification Suite: Whole-Body Controller (WBC) / Arm IK Failure & Atomicity Contract.

This test suite evaluates the single-frame execution boundary between WBC and Arm IK:
- CONTRACT10-01: Normal bilateral arm tracking and feedback verification.
- CONTRACT10-02: CLEANUP_PENDING admission rejection and zero-residue check on WBC root/pelvis.
- CONTRACT10-03: FAILED isolation propagation to WBC and zero-residue check.
- CONTRACT10-04: Arm IK rollback vs WBC prior scene writes (Root/Spine) restoration check.
- CONTRACT10-05: Unreachable hand target truthful error reporting and unmet constraints check.
- CONTRACT10-06: Second hand failure and single-frame bilateral partial-commit atomicity check.

CRITICAL DISCIPLINE:
Per TASK 10-B-15 6/6 instructions, all tests assert strict contract compliance.
Production defects must produce truthful test FAILs without altering assertions,
mocking, skipping, or modifying production code.
"""

from __future__ import annotations

import math
import os
import sys
import unittest
from typing import Optional, Tuple

import bpy
from mathutils import Euler, Vector

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.whole_body_controller import (
    EndEffectorTarget,
    WholeBodyControlResult,
    WholeBodyControlTargets,
    WholeBodyController,
)
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.arm_ik import (
    _ACTIVE_TRANSACTION_STACK,
    _FailedTransactionClass,
    _ISOLATED_FAILED_ARMATURES,
    _PENDING_ARM_RIG_CLEANUPS,
    _arm_rig_transaction,
    _clear_test_fault_injection_hook,
    _set_test_fault_injection_hook,
    _snapshot_arm_rig_state,
    _verify_arm_rig_state_restored,
    ensure_armature_session_identity,
    reset_arm_ik,
    set_hand_ik_target,
    setup_arm_ik,
)
from src.rig.ik import setup_leg_ik
from src.rig.pose import reset_pose


class TestTask10BWBCFailureContract(unittest.TestCase):
    """CONTRACT-10 Verification Suite testing WBC and Arm IK single-frame failure boundaries."""

    def setUp(self) -> None:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.config = PipelineConfig()
        self.char_data = build_character(self.config)
        self.root = self.char_data["root"]
        self.parts = self.char_data["parts"]
        self.armature = build_rig(self.config)
        bind_character_to_rig(self.armature, self.parts)
        setup_leg_ik(self.armature)
        setup_arm_ik(self.armature, initial_influence=0.0)

        self.wbc = WholeBodyController(
            armature_obj=self.armature,
            root_obj=self.root,
            config=self.config,
        )
        _clear_test_fault_injection_hook()

    def tearDown(self) -> None:
        _clear_test_fault_injection_hook()
        _PENDING_ARM_RIG_CLEANUPS.clear()
        _ISOLATED_FAILED_ARMATURES.clear()
        _ACTIVE_TRANSACTION_STACK.clear()

    def test_contract10_01_normal_bilateral_feedback(self) -> None:
        """CONTRACT10-01: 正常双臂反馈.

        验证：
        - 正常返回 WholeBodyControlResult;
        - L/R 反馈独立;
        - 反馈目标与实际腕部世界坐标语义一致;
        - 可达性、位置误差真实计算;
        - success 与 unmet_constraints 一致.
        """
        targets = WholeBodyControlTargets()
        # Reasonable forward-reaching targets for both hands (within 0.56m arm reach)
        targets.set_hand(
            side="L",
            target_world_xyz=(-0.24, -7.80, 1.25),
            rotation_deg=(0.0, 0.0, 0.0),
            weight=1.0,
            enabled=True,
            clamp_reach=True,
        )
        targets.set_hand(
            side="R",
            target_world_xyz=(0.24, -7.80, 1.25),
            rotation_deg=(0.0, 0.0, 0.0),
            weight=1.0,
            enabled=True,
            clamp_reach=True,
        )

        res = self.wbc.execute_frame(targets)

        self.assertIsInstance(res, WholeBodyControlResult)
        self.assertIn("hand_L", res.end_effectors)
        self.assertIn("hand_R", res.end_effectors)

        fb_l = res.end_effectors["hand_L"]
        fb_r = res.end_effectors["hand_R"]

        # L and R feedbacks are independent
        self.assertEqual(fb_l.effector_id, "hand_L")
        self.assertEqual(fb_r.effector_id, "hand_R")
        self.assertNotEqual(fb_l.requested_world_xyz, fb_r.requested_world_xyz)

        # Both targets are reachable within anatomical workspace
        self.assertTrue(fb_l.is_reachable)
        self.assertTrue(fb_r.is_reachable)
        self.assertTrue(res.is_all_reachable)

        # Tracking error within acceptable tolerance
        self.assertLess(fb_l.position_error_m, 0.05)
        self.assertLess(fb_r.position_error_m, 0.05)

        # Success is consistent with empty unmet constraints
        self.assertTrue(res.success)
        self.assertEqual(len(res.unmet_constraints), 0)

    def test_contract10_02_cleanup_pending_admission_rejection(self) -> None:
        """CONTRACT10-02: CLEANUP_PENDING 准入拒绝.

        步骤：
        - 让 Armature 进入 CLEANUP_PENDING.
        - 记录初始 Root 与 Pelvis.
        - 执行包含 Root、Pelvis、Hand L 目标的单帧.
        - 必须验证：
          1. Arm IK 拒绝准入.
          2. WBC 不返回虚假成功结果.
          3. 包含真实失败原因.
          4. Root 和 Pelvis 不留下部分写入（若已修改，测试必须 FAIL）.
          5. Controller 状态不变.
          6. Pending Registry 保留.
          7. 没有新的逻辑提交.
        """
        captured_tx = []
        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_commit_cleanup":
                captured_tx.append(ctx["tx"])
                raise RuntimeError("Simulated cleanup crash for CONTRACT10-02")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError):
                with _arm_rig_transaction(self.armature) as tx_pend:
                    pass
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(len(captured_tx), 1)
        tx = captured_tx[0]
        self.assertEqual(tx.state.value, "CLEANUP_PENDING")
        self.assertIn(tx.tx_id, _PENDING_ARM_RIG_CLEANUPS)

        # Snapshot before WBC execution
        root_loc_before = tuple(round(v, 5) for v in self.root.location)
        p_pelvis = self.armature.pose.bones.get("pelvis")
        pelvis_loc_before = tuple(round(v, 5) for v in p_pelvis.location) if p_pelvis else None
        snap_arm_before = _snapshot_arm_rig_state(self.armature)

        # Configure targets that attempt to modify Root, Pelvis, and activate Hand L
        targets = WholeBodyControlTargets()
        new_root_pos = (0.0, -7.0, 0.0)
        new_pelvis_loc = (0.0, 0.0, 0.15)
        targets.set_root(position=new_root_pos)
        targets.set_pelvis(location=new_pelvis_loc)
        targets.set_hand(
            side="L",
            target_world_xyz=(0.3, -7.7, 1.2),
            weight=1.0,
            enabled=True,
        )

        execution_threw_exception = False
        returned_result: Optional[WholeBodyControlResult] = None
        caught_exception = None

        try:
            returned_result = self.wbc.execute_frame(targets)
        except Exception as exc:
            execution_threw_exception = True
            caught_exception = exc

        # 1. Arm IK must reject admission: execution threw or result failed
        self.assertTrue(
            execution_threw_exception or (returned_result is not None and not returned_result.success),
            "WBC must reject admission under CLEANUP_PENDING",
        )

        # 2. WBC must not return false success
        if returned_result is not None:
            self.assertFalse(returned_result.success, "WBC must not report success under CLEANUP_PENDING")

        # 3. Pending registry intact
        self.assertIn(tx.tx_id, _PENDING_ARM_RIG_CLEANUPS)

        # 4. Root and Pelvis must NOT leave partial writes (CONTRACT-10 strict rule)
        root_loc_after = tuple(round(v, 5) for v in self.root.location)
        pelvis_loc_after = tuple(round(v, 5) for v in p_pelvis.location) if p_pelvis else None

        self.assertEqual(
            root_loc_after,
            root_loc_before,
            f"CONTRACT-10 DEFECT: Root position partially modified ({root_loc_after} != {root_loc_before}) after Arm IK admission rejection",
        )
        self.assertEqual(
            pelvis_loc_after,
            pelvis_loc_before,
            f"CONTRACT-10 DEFECT: Pelvis location partially modified ({pelvis_loc_after} != {pelvis_loc_before}) after Arm IK admission rejection",
        )

        # 5. Controller state untouched
        _verify_arm_rig_state_restored(self.armature, snap_arm_before)

    def test_contract10_03_failed_isolation_propagation_to_wbc(self) -> None:
        """CONTRACT10-03: FAILED Isolation 向 WBC 传播.

        必须验证：
        - WBC 不能绕过 FAILED Gate;
        - 失败原因可追踪;
        - 没有成功结果;
        - 失败隔离记录完整保留;
        - Root、Pelvis 和其他已写入对象符合零残留合同.
        """
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id

        # Drive Armature into FAILED-B isolation
        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                raise RuntimeError("Primary write fault in CONTRACT10-03")
            elif stage == "during_rollback_execution":
                raise RuntimeError("Rollback crash forcing FAILED-B in CONTRACT10-03")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError):
                set_hand_ik_target(self.armature, "L", world_xyz=(0.3, -7.8, 1.2))
        finally:
            _clear_test_fault_injection_hook()

        self.assertIn(session_id, _ISOLATED_FAILED_ARMATURES)
        iso_rec = _ISOLATED_FAILED_ARMATURES[session_id]
        self.assertEqual(iso_rec.get("failure_class"), _FailedTransactionClass.FAILED_B.value)

        root_loc_before = tuple(round(v, 5) for v in self.root.location)
        p_pelvis = self.armature.pose.bones.get("pelvis")
        pelvis_loc_before = tuple(round(v, 5) for v in p_pelvis.location) if p_pelvis else None

        # Attempt to run WBC with Root and Hand L targets
        targets = WholeBodyControlTargets()
        targets.set_root(position=(0.0, -6.8, 0.0))
        targets.set_pelvis(location=(0.0, 0.0, 0.1))
        targets.set_hand(side="L", target_world_xyz=(0.3, -7.7, 1.2), weight=1.0)

        execution_threw = False
        returned_res = None
        try:
            returned_res = self.wbc.execute_frame(targets)
        except Exception:
            execution_threw = True

        # Must not bypass FAILED Gate
        self.assertTrue(execution_threw or (returned_res and not returned_res.success))
        if returned_res is not None:
            self.assertFalse(returned_res.success)

        # Isolation record preserved
        self.assertIn(session_id, _ISOLATED_FAILED_ARMATURES)

        # Root and Pelvis must satisfy zero-residue contract
        root_loc_after = tuple(round(v, 5) for v in self.root.location)
        pelvis_loc_after = tuple(round(v, 5) for v in p_pelvis.location) if p_pelvis else None

        self.assertEqual(
            root_loc_after,
            root_loc_before,
            f"CONTRACT-10 DEFECT: Root position partially modified ({root_loc_after} != {root_loc_before}) during FAILED isolation",
        )
        self.assertEqual(
            pelvis_loc_after,
            pelvis_loc_before,
            f"CONTRACT-10 DEFECT: Pelvis location partially modified ({pelvis_loc_after} != {pelvis_loc_before}) during FAILED isolation",
        )

    def test_contract10_04_arm_ik_rollback_vs_wbc_prior_writes_restoration(self) -> None:
        """CONTRACT10-04: Arm IK 回滚成功，但 WBC 前序写入是否恢复.

        在 WBC 单帧目标中同时设置：
        - Root 位置;
        - Spine 姿态;
        - Hand L 目标.
        对 Arm IK 注入 set_hand_ik_target_after_hand_location 故障，使 Arm IK 局部事务回滚.
        检查：
        - Arm IK 局部快照是否恢复;
        - WBC Root 是否恢复;
        - Spine 是否恢复;
        - 若 Arm IK 已恢复、Root 或 Spine 未恢复，测试必须真实失败.
        """
        root_loc_before = tuple(round(v, 5) for v in self.root.location)
        p_spine = self.armature.pose.bones.get("spine")
        spine_rot_before = tuple(round(v, 5) for v in p_spine.rotation_euler) if p_spine else None
        snap_arm_before = _snapshot_arm_rig_state(self.armature)

        # WBC target modifying Root, Spine, and Hand L
        targets = WholeBodyControlTargets()
        targets.set_root(position=(0.0, -6.5, 0.0))
        targets.spine_rotation_deg = (15.0, 0.0, 0.0)
        targets.set_hand(side="L", target_world_xyz=(0.3, -7.7, 1.2), weight=1.0)

        # Inject Arm IK primary write failure -> triggers clean rollback
        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                raise RuntimeError("Simulated Arm IK write failure in CONTRACT10-04")

        _set_test_fault_injection_hook(fault_hook)
        returned_res = None
        threw_exc = False
        try:
            returned_res = self.wbc.execute_frame(targets)
        except Exception:
            threw_exc = True
        finally:
            _clear_test_fault_injection_hook()

        # Whole-frame atomicity check: Root and Spine must also be restored
        root_loc_after = tuple(round(v, 5) for v in self.root.location)
        spine_rot_after = tuple(round(v, 5) for v in p_spine.rotation_euler) if p_spine else None

        self.assertEqual(
            root_loc_after,
            root_loc_before,
            f"CONTRACT-10 DEFECT: Arm IK rolled back, but WBC Root location remained corrupted ({root_loc_after} != {root_loc_before})",
        )
        self.assertEqual(
            spine_rot_after,
            spine_rot_before,
            f"CONTRACT-10 DEFECT: Arm IK rolled back, but WBC Spine rotation remained corrupted ({spine_rot_after} != {spine_rot_before})",
        )

        # Arm IK local transaction must have cleanly rolled back
        _verify_arm_rig_state_restored(self.armature, snap_arm_before)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_contract10_05_unreachable_hand_target_feedback(self) -> None:
        """CONTRACT10-05: 不可达手部目标反馈.

        使用真实不可达目标 (clamp_reach=False).
        验证：
        - WBC 实际报告的可达性;
        - Hand L / Hand R 独立反馈;
        - success 不得错误为 True;
        - unmet_constraints 包含对应末端;
        - 实际位置与目标误差未被伪造为零.
        """
        targets = WholeBodyControlTargets()
        # Extremely far target impossible for humanoid arm to reach
        targets.set_hand(
            side="L",
            target_world_xyz=(10.0, 10.0, 10.0),
            weight=1.0,
            enabled=True,
            clamp_reach=False,
        )

        res = self.wbc.execute_frame(targets)

        # 1. Overall reachability flag
        self.assertFalse(res.is_all_reachable, "WholeBodyControlResult.is_all_reachable must be False for 10m target")

        # 2. Hand L feedback
        self.assertIn("hand_L", res.end_effectors)
        fb_l = res.end_effectors["hand_L"]
        self.assertFalse(fb_l.is_reachable, "EndEffectorFeedback.is_reachable must be False")
        self.assertGreater(fb_l.position_error_m, 1.0, "Position error must be truthful (> 1.0m)")

        # 3. success must be False
        self.assertFalse(res.success, "WholeBodyControlResult.success must be False when constraint is unmet")

        # 4. unmet_constraints must list hand_L
        self.assertGreater(len(res.unmet_constraints), 0)
        unmet_names = [uc.target_name for uc in res.unmet_constraints]
        self.assertIn("hand_L", unmet_names, "unmet_constraints must contain hand_L")

    def test_contract10_06_second_hand_failure_bilateral_partial_commit(self) -> None:
        """CONTRACT10-06: 第二只手失败后的单帧状态.

        同一帧设置左右手目标.
        让左手先执行，右手随后发生受控异常.
        检查：
        - 左手 Controller;
        - 右手 Controller;
        - L/R Constraint Influence;
        - Root 和 Pelvis;
        - WBC 是否给出成功结果;
        - 是否存在一个手已经提交、另一个手失败的情况.
        """
        snap_before = _snapshot_arm_rig_state(self.armature)

        targets = WholeBodyControlTargets()
        targets.set_hand(side="L", target_world_xyz=(0.25, -7.75, 1.20), weight=1.0, enabled=True)
        targets.set_hand(side="R", target_world_xyz=(-0.25, -7.75, 1.20), weight=1.0, enabled=True)

        # Inject failure specifically when setting Right hand target
        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                side = ctx.get("side")
                if side == "R":
                    raise RuntimeError("Simulated Right Hand write fault in CONTRACT10-06")

        _set_test_fault_injection_hook(fault_hook)
        returned_res = None
        threw_exc = False
        try:
            returned_res = self.wbc.execute_frame(targets)
        except Exception:
            threw_exc = True
        finally:
            _clear_test_fault_injection_hook()

        # If a result was returned, success must not be True
        if returned_res is not None:
            self.assertFalse(returned_res.success)

        # Bilateral atomicity check:
        # If right hand failed mid-frame, left hand must not remain committed as a partial write
        p_fore_l = self.armature.pose.bones["forearm.L"]
        p_fore_r = self.armature.pose.bones["forearm.R"]
        con_l = p_fore_l.constraints.get("ArmIK.L")
        con_r = p_fore_r.constraints.get("ArmIK.R")

        inf_l = con_l.influence if con_l else 0.0
        inf_r = con_r.influence if con_r else 0.0

        # CONTRACT-10 rule: Frame must be atomic; L and R must not be in divergent half-committed state
        self.assertEqual(
            inf_l,
            0.0,
            f"CONTRACT-10 DEFECT: Left hand remained committed (influence={inf_l}) when Right hand failed mid-frame",
        )
        self.assertEqual(
            inf_r,
            0.0,
            f"CONTRACT-10 DEFECT: Right hand constraint influence corrupted (influence={inf_r})",
        )

        # Rig state as a whole should match pre-frame snapshot
        _verify_arm_rig_state_restored(self.armature, snap_before)


if __name__ == "__main__":
    args = [sys.argv[0]]
    if "--" in sys.argv:
        args.extend(sys.argv[sys.argv.index("--") + 1:])
    else:
        args.append("-v")
    unittest.main(argv=args)
