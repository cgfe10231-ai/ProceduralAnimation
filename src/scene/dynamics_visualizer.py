"""Dynamics Playground Real Dynamics State Integration & Visualization (Task 6G-D-C2-A).

Integrates verified numerical closed-loop dynamics simulation results into
Blender's `output/dynamics_playground.blend` training ground scene.

Features:
- Pure Python numerical scenario generator: 100% decoupled from bpy for headless verification.
- 5 Physical Verification Scenarios:
  1. Static Support Equilibrium: CoM height held rock-solid by ground reaction forces.
  2. Gravity Free-Fall: Unassisted gravitational drop under -9.81 m/s^2, zero contact forces.
  3. Horizontal Acceleration: Propulsion forces within Coulomb friction cone driving forward translation.
  4. Insufficient Friction Clamping: Forces clamped at friction limit (mu=0.08), showing visual slip & lag vs target ghost.
  5. Eccentric Contact Rotation: Off-center contact produces net roll torque, driving attitude tilt & angular momentum.
- Dedicated Visual Hierarchy in Blender:
  - Isolated collection: `Playground_Dynamics_Visualization` (in compliance with ACG Section 6).
  - CoM indicator spheres and oriented rigid-body proxy meshes.
  - Target ghost markers explicitly demonstrating tracking deviations.
  - Dynamic contact force arrows whose orientation and length are 100% bound to real physics outputs.
  - Dynamic angular momentum arrows and 3D trajectory path ribbons.
  - 3D Station text markers and dedicated `DynamicsInspectionCam`.
"""

from __future__ import annotations

import math
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.motion.contact_dynamics import Vec3, vec3_length
from src.motion.contact_force_solver import (
    ContactConstraintSpec,
    ContactSolverConfig,
    ContactSolverStatus,
)
from src.motion.forward_dynamics import (
    ForwardDynamicsConfig,
    ForwardDynamicsState,
    InertiaTensor3x3,
)
from src.motion.closed_loop_dynamics import (
    ClosedLoopAdmissibilityPolicy,
    ClosedLoopControllerConfig,
    ClosedLoopDynamicsCoordinator,
    ClosedLoopSimulationTrajectory,
    DesiredMotionReference,
)
from src.scene.environment_query import (
    DynamicsEnvironmentQuery,
    create_standard_dynamics_playground_query,
)


# =============================================================================
# 1. Pure Python Numerical Simulation Scenarios (100% Decoupled from bpy)
# =============================================================================

def quat_from_z_to_vector(v: Sequence[float]) -> Tuple[Tuple[float, float, float, float], float]:
    """Compute unit quaternion rotating default local +Z axis into 3D direction vector v."""
    vx, vy, vz = float(v[0]), float(v[1]), float(v[2])
    mag = math.sqrt(vx * vx + vy * vy + vz * vz)
    if mag < 1e-8:
        return (1.0, 0.0, 0.0, 0.0), 0.0
    nx, ny, nz = vx / mag, vy / mag, vz / mag
    dot = nz  # dot with (0, 0, 1)
    if dot > 0.9999999:
        return (1.0, 0.0, 0.0, 0.0), mag
    elif dot < -0.9999999:
        return (0.0, 1.0, 0.0, 0.0), mag  # 180 deg around X
    qw = 1.0 + dot
    qx, qy, qz = -ny, nx, 0.0
    qlen = math.sqrt(qw * qw + qx * qx + qy * qy + qz * qz)
    return (qw / qlen, qx / qlen, qy / qlen, qz / qlen), mag


def run_dynamics_scenarios(
    num_steps: int = 72,
    dt: float = 1.0 / 24.0,
    env_query: Optional[DynamicsEnvironmentQuery] = None,
) -> Dict[str, Any]:
    """Execute all 5 core dynamics verification scenarios via numerical integration.

    Parameters:
        num_steps: Total frames to simulate (default 72 frames = 3.0 seconds at 24 fps).
        dt: Timestep (1/24s).
        env_query: Optional DynamicsEnvironmentQuery.

    Returns:
        Dictionary containing trajectory, telemetry, and numerical results for each scenario.
    """
    if env_query is None:
        env_query = create_standard_dynamics_playground_query()

    mass = 70.0
    default_inertia = InertiaTensor3x3.from_diagonal(10.0, 12.0, 15.0)
    coord = ClosedLoopDynamicsCoordinator(config=ClosedLoopControllerConfig(dt=dt))

    scenarios_data: Dict[str, Any] = {}

    # -------------------------------------------------------------------------
    # Scenario 1: Static Support Equilibrium
    # -------------------------------------------------------------------------
    s1_x, s1_y = -3.0, -4.0
    q_s1_L = env_query.query_spatial_surface((s1_x, s1_y + 0.15, 0.0))
    q_s1_R = env_query.query_spatial_surface((s1_x, s1_y - 0.15, 0.0))

    s1_contacts = [
        ContactConstraintSpec(
            contact_id="foot_L",
            contact_point_world=q_s1_L.contact_point_world,
            surface_normal_world=q_s1_L.surface_normal_world,
            friction_coeff=q_s1_L.friction_coeff,
        ),
        ContactConstraintSpec(
            contact_id="foot_R",
            contact_point_world=q_s1_R.contact_point_world,
            surface_normal_world=q_s1_R.surface_normal_world,
            friction_coeff=q_s1_R.friction_coeff,
        ),
    ]

    s1_init_state = ForwardDynamicsState(
        timestamp=0.0,
        mass=mass,
        com_position_world=(s1_x, s1_y, 1.0),
        com_velocity_world=(0.0, 0.0, 0.0),
        angular_momentum_about_com_world=(0.0, 0.0, 0.0),
        orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
        inertia_tensor_body=default_inertia,
    )
    s1_ref = DesiredMotionReference(target_com_position_world=(s1_x, s1_y, 1.0))
    s1_traj = coord.simulate(s1_init_state, s1_ref, s1_contacts, num_steps=num_steps)

    scenarios_data["scenario_1_static_support"] = {
        "title": "Station 1: Static Support Equilibrium",
        "description": "Gravity balanced by normal ground reaction; zero sinkage (< 1e-5m)",
        "station_origin": (s1_x, s1_y, 0.0),
        "trajectory": s1_traj,
        "contacts": s1_contacts,
        "has_angular_momentum": False,
    }

    # -------------------------------------------------------------------------
    # Scenario 2: Gravity Free-Fall
    # -------------------------------------------------------------------------
    s2_x, s2_y = -3.0, -2.0
    s2_z0 = 3.5
    s2_init_state = ForwardDynamicsState(
        timestamp=0.0,
        mass=mass,
        com_position_world=(s2_x, s2_y, s2_z0),
        com_velocity_world=(0.0, 0.0, 0.0),
        angular_momentum_about_com_world=(0.0, 0.0, 0.0),
        orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
        inertia_tensor_body=default_inertia,
    )
    # Demands holding at z=3.5 (hover demand) -> infeasible in mid-air
    s2_ref = DesiredMotionReference(target_com_position_world=(s2_x, s2_y, s2_z0))
    # Airborne for 20 frames, reaching z ~ 0.09m
    s2_traj = coord.simulate(s2_init_state, s2_ref, contact_schedule=[], num_steps=num_steps)

    scenarios_data["scenario_2_free_fall"] = {
        "title": "Station 2: Gravity Free-Fall",
        "description": "Unassisted gravitational drop under -9.81 m/s^2; zero contact forces",
        "station_origin": (s2_x, s2_y, 0.0),
        "trajectory": s2_traj,
        "contacts": [],
        "has_angular_momentum": False,
    }

    # -------------------------------------------------------------------------
    # Scenario 3: Horizontal Acceleration under Admissible Friction
    # -------------------------------------------------------------------------
    s3_x0, s3_y = -6.0, 0.0
    s3_init_state = ForwardDynamicsState(
        timestamp=0.0,
        mass=mass,
        com_position_world=(s3_x0, s3_y, 1.0),
        com_velocity_world=(0.0, 0.0, 0.0),
        angular_momentum_about_com_world=(0.0, 0.0, 0.0),
        orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
        inertia_tensor_body=default_inertia,
    )

    def s3_ref_sched(k: int, t: float, s: ForwardDynamicsState) -> DesiredMotionReference:
        ax = 1.5 if k < 48 else 0.0
        # Analytical position target
        if t <= 2.0:
            target_x = s3_x0 + 0.5 * 1.5 * (t ** 2)
            target_vx = 1.5 * t
        else:
            target_x = s3_x0 + 3.0 + 3.0 * (t - 2.0)
            target_vx = 3.0
        return DesiredMotionReference(
            target_com_position_world=(target_x, s3_y, 1.0),
            target_com_velocity_world=(target_vx, 0.0, 0.0),
            target_linear_acceleration_world=(ax, 0.0, 0.0),
        )

    def s3_contacts_sched(k: int, t: float, s: ForwardDynamicsState) -> Sequence[ContactConstraintSpec]:
        curr_x = s.com_position_world[0]
        return [
            ContactConstraintSpec(
                contact_id="foot_L",
                contact_point_world=(curr_x, s3_y + 0.15, 0.0),
                surface_normal_world=(0.0, 0.0, 1.0),
                friction_coeff=0.65,
            ),
            ContactConstraintSpec(
                contact_id="foot_R",
                contact_point_world=(curr_x, s3_y - 0.15, 0.0),
                surface_normal_world=(0.0, 0.0, 1.0),
                friction_coeff=0.65,
            ),
        ]

    s3_traj = coord.simulate(s3_init_state, s3_ref_sched, s3_contacts_sched, num_steps=num_steps)

    scenarios_data["scenario_3_horizontal_acceleration"] = {
        "title": "Station 3: Horizontal Acceleration",
        "description": "Propulsion forces within friction cone; tracks target with zero lag",
        "station_origin": (s3_x0, s3_y, 0.0),
        "trajectory": s3_traj,
        "ref_sched": s3_ref_sched,
        "contacts_sched": s3_contacts_sched,
        "has_angular_momentum": False,
    }

    # -------------------------------------------------------------------------
    # Scenario 4: Insufficient Friction Clamping (Slip & Lag)
    # -------------------------------------------------------------------------
    s4_x0, s4_y = -6.0, 2.0
    s4_init_state = ForwardDynamicsState(
        timestamp=0.0,
        mass=mass,
        com_position_world=(s4_x0, s4_y, 1.0),
        com_velocity_world=(0.0, 0.0, 0.0),
        angular_momentum_about_com_world=(0.0, 0.0, 0.0),
        orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
        inertia_tensor_body=default_inertia,
    )

    # Demands ax = 2.0 m/s^2 on low friction mu = 0.08 ice surface
    def s4_ref_sched(k: int, t: float, s: ForwardDynamicsState) -> DesiredMotionReference:
        target_x = s4_x0 + 1.0 * (t ** 2)
        target_vx = 2.0 * t
        return DesiredMotionReference(
            target_com_position_world=(target_x, s4_y, 1.0),
            target_com_velocity_world=(target_vx, 0.0, 0.0),
            target_linear_acceleration_world=(2.0, 0.0, 0.0),
        )

    def s4_contacts_sched(k: int, t: float, s: ForwardDynamicsState) -> Sequence[ContactConstraintSpec]:
        curr_x = s.com_position_world[0]
        return [
            ContactConstraintSpec(
                contact_id="foot_L",
                contact_point_world=(curr_x, s4_y + 0.15, 0.0),
                surface_normal_world=(0.0, 0.0, 1.0),
                friction_coeff=0.08,  # Ice patch
            ),
            ContactConstraintSpec(
                contact_id="foot_R",
                contact_point_world=(curr_x, s4_y - 0.15, 0.0),
                surface_normal_world=(0.0, 0.0, 1.0),
                friction_coeff=0.08,
            ),
        ]

    s4_traj = coord.simulate(s4_init_state, s4_ref_sched, s4_contacts_sched, num_steps=num_steps)

    scenarios_data["scenario_4_insufficient_friction"] = {
        "title": "Station 4: Insufficient Friction Clamping",
        "description": "Tangential forces clamped at mu*Fn; visual slip and lag vs target ghost",
        "station_origin": (s4_x0, s4_y, 0.0),
        "trajectory": s4_traj,
        "ref_sched": s4_ref_sched,
        "contacts_sched": s4_contacts_sched,
        "has_angular_momentum": False,
    }

    # -------------------------------------------------------------------------
    # Scenario 5: Eccentric Contact Causing Rotation
    # -------------------------------------------------------------------------
    s5_x, s5_y = -3.0, 4.0
    s5_init_state = ForwardDynamicsState(
        timestamp=0.0,
        mass=mass,
        com_position_world=(s5_x, s5_y, 1.0),
        com_velocity_world=(0.0, 0.0, 0.0),
        angular_momentum_about_com_world=(0.0, 0.0, 0.0),
        orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
        inertia_tensor_body=default_inertia,
    )
    # Contact eccentrically offset by ry = -0.3m (creating roll torque tau_x = -0.3 * 686.7 ~ -206 N*m)
    s5_contact = ContactConstraintSpec(
        contact_id="eccentric_foot",
        contact_point_world=(s5_x, s5_y - 0.30, 0.0),
        surface_normal_world=(0.0, 0.0, 1.0),
        friction_coeff=0.65,
    )
    s5_ref = DesiredMotionReference(target_com_position_world=(s5_x, s5_y, 1.0))
    s5_traj = coord.simulate(s5_init_state, s5_ref, [s5_contact], num_steps=num_steps)

    scenarios_data["scenario_5_eccentric_rotation"] = {
        "title": "Station 5: Eccentric Contact Rotation",
        "description": "Eccentric lever arm creates net roll torque; rotates body attitude and builds L_x",
        "station_origin": (s5_x, s5_y, 0.0),
        "trajectory": s5_traj,
        "contacts": [s5_contact],
        "has_angular_momentum": True,
    }

    return scenarios_data


# =============================================================================
# 2. Blender 3D Scene Injection & Keyframing (Requires bpy)
# =============================================================================

def get_or_create_material(name: str, color_rgba: Tuple[float, float, float, float], roughness: float = 0.5, alpha: float = 1.0):
    """Retrieve or create Blender material with Principled BSDF shader."""
    import bpy
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = color_rgba
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
            if alpha < 0.999 and "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = alpha
                mat.blend_method = "BLEND"
    return mat


def create_arrow_mesh_data(name: str, length: float = 1.0, stem_radius: float = 0.025, head_length: float = 0.15, head_radius: float = 0.065):
    """Generate reusable unit arrow mesh pointing along local +Z axis with base at (0, 0, 0)."""
    import bpy
    existing = bpy.data.meshes.get(name)
    if existing:
        return existing

    num_sides = 8
    stem_len = max(0.05, length - head_length)
    verts = []
    # Base ring 0
    for i in range(num_sides):
        ang = 2.0 * math.pi * i / num_sides
        verts.append((stem_radius * math.cos(ang), stem_radius * math.sin(ang), 0.0))
    # Stem top ring 1
    for i in range(num_sides):
        ang = 2.0 * math.pi * i / num_sides
        verts.append((stem_radius * math.cos(ang), stem_radius * math.sin(ang), stem_len))
    # Head base ring 2
    for i in range(num_sides):
        ang = 2.0 * math.pi * i / num_sides
        verts.append((head_radius * math.cos(ang), head_radius * math.sin(ang), stem_len))
    # Tip vertex
    tip_idx = len(verts)
    verts.append((0.0, 0.0, length))

    faces = []
    for i in range(num_sides):
        i_next = (i + 1) % num_sides
        # Stem quad
        faces.append((i, i_next, num_sides + i_next, num_sides + i))
        # Head cone triangle
        faces.append((2 * num_sides + i, 2 * num_sides + i_next, tip_idx))
        # Head collar
        faces.append((num_sides + i, num_sides + i_next, 2 * num_sides + i_next, 2 * num_sides + i))

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return mesh


def inject_dynamics_visualization(
    scene: Any,
    scenarios_data: Dict[str, Any],
    collection_name: str = "Playground_Dynamics_Visualization",
) -> Any:
    """Instantiate and keyframe all 5 physical dynamics scenarios in the Blender scene.

    Preserves existing surface and visual collections completely intact.
    All dynamic indicators are linked into the dedicated `Playground_Dynamics_Visualization` collection.
    """
    import bpy

    # 1. Ensure dedicated collection
    viz_col = bpy.data.collections.get(collection_name)
    if not viz_col:
        viz_col = bpy.data.collections.new(collection_name)
        scene.collection.children.link(viz_col)
    else:
        # Clean previous dynamics visual objects from collection
        for obj in list(viz_col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    # 2. Reusable Materials
    mat_com = get_or_create_material("Mat_Dynamics_CoM", (0.0, 0.75, 1.0, 1.0), roughness=0.3)
    mat_body = get_or_create_material("Mat_Dynamics_BodyProxy", (0.15, 0.35, 0.75, 0.9), roughness=0.4)
    mat_ghost = get_or_create_material("Mat_Dynamics_TargetGhost", (1.0, 0.85, 0.1, 0.35), roughness=0.6, alpha=0.35)
    mat_contact = get_or_create_material("Mat_Dynamics_ContactDisc", (0.95, 0.45, 0.1, 1.0), roughness=0.5)
    mat_force = get_or_create_material("Mat_Dynamics_ForceArrow", (0.15, 0.95, 0.25, 1.0), roughness=0.3)
    mat_ang_mom = get_or_create_material("Mat_Dynamics_AngMomArrow", (0.95, 0.15, 0.85, 1.0), roughness=0.3)

    # Unit arrow mesh
    unit_arrow_mesh = create_arrow_mesh_data("Mesh_Dynamics_UnitArrow", length=1.0)

    # Force scale: 500 N = 1.0 m arrow length
    force_scale = 1.0 / 500.0
    ang_mom_scale = 1.0 / 500.0

    # 3. Setup timeline
    scene.frame_start = 1
    scene.frame_end = 73
    scene.frame_current = 1

    scenario_keys = list(scenarios_data.keys())

    for s_idx, s_key in enumerate(scenario_keys, 1):
        s_data = scenarios_data[s_key]
        traj: ClosedLoopSimulationTrajectory = s_data["trajectory"]
        frames = traj.frames
        station_x, station_y, _ = s_data["station_origin"]

        # A. Station Ground Text Label
        bpy.ops.object.text_add(location=(station_x - 1.2, station_y - 0.7, 0.02))
        lbl_obj = bpy.context.active_object
        lbl_obj.name = f"Station_{s_idx}_Label"
        lbl_obj.data.body = s_data["title"]
        lbl_obj.data.size = 0.22
        lbl_obj.data.extrude = 0.02
        lbl_obj.rotation_euler = (0.0, 0.0, 0.0)
        scene.collection.objects.unlink(lbl_obj)
        viz_col.objects.link(lbl_obj)

        # B. CoM Sphere
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.08, location=(0, 0, 0))
        com_obj = bpy.context.active_object
        com_obj.name = f"Dynamics_CoM_S{s_idx}"
        com_obj.data.materials.append(mat_com)
        scene.collection.objects.unlink(com_obj)
        viz_col.objects.link(com_obj)

        # C. Body Proxy Box (Aggregate rigid body indicator)
        bpy.ops.mesh.primitive_cube_add(size=1.0, scale=(0.30, 0.22, 0.45), location=(0, 0, 0))
        body_obj = bpy.context.active_object
        body_obj.name = f"Dynamics_BodyProxy_S{s_idx}"
        body_obj.rotation_mode = "QUATERNION"
        body_obj.data.materials.append(mat_body)
        scene.collection.objects.unlink(body_obj)
        viz_col.objects.link(body_obj)

        # D. Target Ghost (Wireframe/transparent marker)
        bpy.ops.mesh.primitive_cube_add(size=1.0, scale=(0.32, 0.24, 0.47), location=(0, 0, 0))
        ghost_obj = bpy.context.active_object
        ghost_obj.name = f"Dynamics_TargetGhost_S{s_idx}"
        ghost_obj.data.materials.append(mat_ghost)
        scene.collection.objects.unlink(ghost_obj)
        viz_col.objects.link(ghost_obj)

        # E. Angular Momentum Arrow (if applicable)
        ang_mom_obj = None
        if s_data.get("has_angular_momentum", False):
            ang_mom_obj = bpy.data.objects.new(f"Dynamics_AngMomArrow_S{s_idx}", unit_arrow_mesh)
            ang_mom_obj.rotation_mode = "QUATERNION"
            ang_mom_obj.data.materials.append(mat_ang_mom)
            viz_col.objects.link(ang_mom_obj)

        # F. Contact Points & Force Arrows
        # Determine unique contact IDs across frames
        unique_cids = set()
        for f in frames:
            for cid in f.actual_contact_forces.keys():
                unique_cids.add(cid)

        contact_objs: Dict[str, Tuple[bpy.types.Object, bpy.types.Object]] = {}
        for cid in sorted(unique_cids):
            # Disc
            bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=0.015, location=(0, 0, 0))
            disc_obj = bpy.context.active_object
            disc_obj.name = f"Dynamics_ContactDisc_S{s_idx}_{cid}"
            disc_obj.data.materials.append(mat_contact)
            scene.collection.objects.unlink(disc_obj)
            viz_col.objects.link(disc_obj)

            # Dynamic Force Arrow
            arrow_obj = bpy.data.objects.new(f"Dynamics_ForceArrow_S{s_idx}_{cid}", unit_arrow_mesh)
            arrow_obj.rotation_mode = "QUATERNION"
            arrow_obj.data.materials.append(mat_force)
            viz_col.objects.link(arrow_obj)

            contact_objs[cid] = (disc_obj, arrow_obj)

        # Build 73 chronological states: S0 (t=0) at frame 1 ... S72 (t=3.0s) at frame 73
        timeline_samples = []
        dt = 1.0 / 24.0

        for k, frame_telem in enumerate(frames):
            curr_state = frame_telem.state_current
            if "contacts_sched" in s_data:
                c_list = s_data["contacts_sched"](k, frame_telem.timestamp, curr_state)
            else:
                c_list = s_data.get("contacts", [])
            c_map = {c.contact_id: c.contact_point_world for c in c_list}

            timeline_samples.append({
                "frame": k + 1,
                "timestamp": frame_telem.timestamp,
                "state": curr_state,
                "target_pos": frame_telem.motion_reference.target_com_position_world or curr_state.com_position_world,
                "contact_pos_map": c_map,
                "contact_forces": frame_telem.actual_contact_forces,
            })

        # Terminal state S72 at t = 72 * dt = 3.0s (frame 73)
        final_state = traj.final_state
        final_t = 72 * dt
        last_step = frames[-1]
        if "ref_sched" in s_data:
            term_ref = s_data["ref_sched"](72, final_t, final_state)
            term_tgt = term_ref.target_com_position_world or final_state.com_position_world
        else:
            term_tgt = last_step.motion_reference.target_com_position_world or final_state.com_position_world

        if "contacts_sched" in s_data:
            final_c_list = s_data["contacts_sched"](72, final_t, final_state)
        else:
            final_c_list = s_data.get("contacts", [])
        final_c_map = {c.contact_id: c.contact_point_world for c in final_c_list}

        timeline_samples.append({
            "frame": 73,
            "timestamp": final_t,
            "state": final_state,
            "target_pos": term_tgt,
            "contact_pos_map": final_c_map,
            "contact_forces": last_step.actual_contact_forces,
        })

        # G. Trajectory Spline Curve (73 points)
        curve_data = bpy.data.curves.new(f"Dynamics_TrajectoryData_S{s_idx}", type="CURVE")
        curve_data.dimensions = "3D"
        curve_data.bevel_depth = 0.015
        polyline = curve_data.splines.new("POLY")
        polyline.points.add(len(timeline_samples) - 1)

        traj_obj = bpy.data.objects.new(f"Dynamics_Trajectory_S{s_idx}", curve_data)
        traj_obj.data.materials.append(mat_com)
        viz_col.objects.link(traj_obj)

        # ---------------------------------------------------------------------
        # Keyframing Loop Across 73 Standardized States (S0 at F1 ... S72 at F73)
        # ---------------------------------------------------------------------
        for sample in timeline_samples:
            f_idx = sample["frame"]
            curr_state = sample["state"]
            p_actual = curr_state.com_position_world
            q_actual = curr_state.orientation_quat_world

            # 1. Update Trajectory Spline Point
            polyline.points[f_idx - 1].co = (p_actual[0], p_actual[1], p_actual[2], 1.0)

            # 2. CoM Sphere Location
            com_obj.location = p_actual
            com_obj.keyframe_insert("location", frame=f_idx)

            # 3. Body Proxy Position & Attitude
            body_obj.location = p_actual
            body_obj.rotation_quaternion = q_actual
            body_obj.keyframe_insert("location", frame=f_idx)
            body_obj.keyframe_insert("rotation_quaternion", frame=f_idx)

            # 4. Target Ghost Position
            p_target = sample["target_pos"]
            ghost_obj.location = p_target
            ghost_obj.keyframe_insert("location", frame=f_idx)

            # 5. Angular Momentum Arrow
            if ang_mom_obj:
                L = curr_state.angular_momentum_about_com_world
                q_L, mag_L = quat_from_z_to_vector(L)
                ang_mom_obj.location = p_actual
                ang_mom_obj.rotation_quaternion = q_L
                scale_L = mag_L * ang_mom_scale
                if scale_L < 1e-4:
                    ang_mom_obj.scale = (0.0, 0.0, 0.0)
                else:
                    ang_mom_obj.scale = (1.0, 1.0, scale_L)
                ang_mom_obj.keyframe_insert("location", frame=f_idx)
                ang_mom_obj.keyframe_insert("rotation_quaternion", frame=f_idx)
                ang_mom_obj.keyframe_insert("scale", frame=f_idx)

            # 6. Contact Discs and Force Arrows
            c_pos_map = sample["contact_pos_map"]
            forces_map = sample["contact_forces"]

            for cid, (disc, arrow) in contact_objs.items():
                if cid in c_pos_map:
                    cp = c_pos_map[cid]
                    disc.location = cp
                    disc.scale = (1.0, 1.0, 1.0)
                else:
                    disc.scale = (0.0, 0.0, 0.0)
                disc.keyframe_insert("location", frame=f_idx)
                disc.keyframe_insert("scale", frame=f_idx)

                # Force Arrow
                force_vec = forces_map.get(cid, (0.0, 0.0, 0.0))
                q_f, mag_f = quat_from_z_to_vector(force_vec)
                arrow.location = c_pos_map.get(cid, (0.0, 0.0, 0.0))
                arrow.rotation_quaternion = q_f
                scale_f = mag_f * force_scale
                if scale_f < 1e-4:
                    arrow.scale = (0.0, 0.0, 0.0)
                else:
                    arrow.scale = (1.0, 1.0, scale_f)
                arrow.keyframe_insert("location", frame=f_idx)
                arrow.keyframe_insert("rotation_quaternion", frame=f_idx)
                arrow.keyframe_insert("scale", frame=f_idx)

    # 4. Create Dedicated Inspection Camera
    cam_name = "DynamicsInspectionCam"
    insp_cam = bpy.data.objects.get(cam_name)
    if not insp_cam:
        cam_data = bpy.data.cameras.new(cam_name)
        cam_data.lens = 32.0  # Wide angle to frame all 5 stations
        cam_data.clip_start = 0.1
        cam_data.clip_end = 100.0
        insp_cam = bpy.data.objects.new(cam_name, cam_data)
        viz_col.objects.link(insp_cam)

    # Positioned at elevated isometric vantage point looking toward the flat stations
    insp_cam.location = (4.5, 0.0, 6.2)
    # Rotation pointing toward (-4.0, 0.0, 1.0): tilt ~ 55 deg
    insp_cam.rotation_euler = (math.radians(58.0), 0.0, math.radians(90.0))

    # Keep PlaygroundOverviewCam as primary scene camera for regression compatibility
    cam_over = bpy.data.objects.get("PlaygroundOverviewCam")
    if cam_over:
        scene.camera = cam_over
    else:
        scene.camera = insp_cam

    return viz_col


def build_and_save_playground_with_dynamics(blend_path: str) -> Dict[str, Any]:
    """Load existing output/dynamics_playground.blend, inject dynamics, and save.

    Preserves 100% of existing surfaces, visuals, and lighting objects.
    """
    import bpy

    if not os.path.isfile(blend_path):
        raise FileNotFoundError(f"Target dynamics playground blend not found: {blend_path}")

    # 1. Open existing blend
    bpy.ops.wm.open_mainfile(filepath=blend_path)
    scene = bpy.context.scene

    # 2. Run numerical scenarios
    scenarios_data = run_dynamics_scenarios(num_steps=72, dt=1.0 / 24.0)

    # 3. Inject visual keyframes into dedicated collection
    inject_dynamics_visualization(scene, scenarios_data)

    # 4. Save file back to disk
    bpy.ops.wm.save_mainfile(filepath=blend_path)
    return scenarios_data
