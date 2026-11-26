# ProceduralAnimation Test Execution Report

> **Execution Date**: 2026-11-10 00:53:45
> **Target Tier**: `quick`
> **Overall Result**: **ALL PASSED**
> **Execution Summary**: Total Planned: 19 | Executed: 19 | Passed: 19 (Automated Pass: 3) | Failed: 0 | Skipped: 0 (Req: 0, Opt: 0) | Not Run: 0 | Duration: 45.94s

---

## Test Results Table

| Test ID | Test Name | Runner | Status | Duration | Failure / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `architecture_integrity_gate` | Architecture Documentation Integrity & Symbol Existence Gate | `python` | **PASSED** | 1.16s | - |
| `spatial_layout_clearance` | Spatial Corridor Clearance & Math Layout | `blender_headless` | **PASSED** | 1.52s | - |
| `dynamics_environment_query` | Dynamics Environment Query & 3D Surface Geometry | `python` | **PASSED** | 0.58s | - |
| `contact_dynamics_math` | Contact Dynamics Foundation & Momentum Impulse | `python` | **PASSED** | 0.57s | - |
| `contact_force_solver` | Multi-Contact Force Solver & Constraint Allocation | `python` | **PASSED** | 0.66s | - |
| `forward_dynamics` | Forward Dynamics Single-Step Integration Kernel | `python` | **PASSED** | 0.61s | - |
| `closed_loop_dynamics` | Multi-Frame Dynamics Closed-Loop Control & State Feedback | `python` | **PASSED** | 1.12s | - |
| `runner_unit_tests` | Test Suite Runner Unit Tests | `python` | **PASSED** | 1.21s | - |
| `physics_joint_limits` | Anatomical Joint ROM Limit Verification | `blender_headless` | **PASSED** | 1.6s | - |
| `physics_rigid_link_com` | Rigid Link Segments & Whole-Body CoM | `blender_headless` | **PASSED** | 1.56s | - |
| `mesh_environment_query` | Environment Gate 01: Blender Mesh Environment Adapter & Data Authenticity | `blender_headless` | **PASSED** | 3.86s | - |
| `task7a2_p0_teleport_regression` | Task 7A-2 P0: Detection & Prevention of Frame 226->227 Teleportation Defect | `blender_headless` | **PASSED** | 2.12s | - |
| `task7a2_negative_invariance` | Task 7A-2: Terrain Walk Invariance & Negative Physics Verification | `blender_headless` | **PASSED** | 1.52s | - |
| `environment_gate01_unit3` | Environment Gate 01 / Unit 3: Real Mesh BVH Integration & Counter-Factual Verification | `blender_headless` | **AUTOMATED_PASS** | 13.34s | Visual Inspection Required |
| `environment_gate01_u3_s1` | Environment Gate 01 / Unit 3-S1: Root Forward Motion Continuity Across Alternating Footsteps | `blender_headless` | **AUTOMATED_PASS** | 4.32s | Visual Inspection Required |
| `environment_gate01_u3_s2` | Environment Gate 01 / Unit 3-S2: Swing-to-Stance Landing Continuity Repair | `blender_headless` | **AUTOMATED_PASS** | 4.3s | Visual Inspection Required |
| `environment_gate01_unit4` | Environment Gate 01 / Unit 4: Real Mesh Contact Elevation & Consistency | `blender_headless` | **PASSED** | 1.9s | - |
| `environment_gate01_unit4_closure` | Environment Gate 01 / Unit 4: Non-Support Rejection & Analytical Fallback Closure | `blender_headless` | **PASSED** | 1.81s | - |
| `terrain_planning_contract` | Terrain Planning Joint Repair: Direction, Seam, and Timebase Contracts | `blender_headless` | **PASSED** | 2.18s | - |
