# ProceduralAnimation Test Execution Report

> **Execution Date**: 2026-11-27 17:56:04  
> **Target Tier**: `quick`  
> **Overall Result**: **ALL PASSED**  
> **Execution Summary**: Total Planned: 19 | Executed: 19 | Passed: 19 (Automated Pass: 3) | Failed: 0 | Skipped: 0 (Req: 0, Opt: 0) | Not Run: 0 | Duration: 78.26s

---

## Test Results Table

| Test ID | Test Name | Runner | Status | Duration | Failure / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `architecture_integrity_gate` | Architecture Documentation Integrity & Symbol Existence Gate | `python` | **PASSED** | 2.53s | - |
| `spatial_layout_clearance` | Spatial Corridor Clearance & Math Layout | `blender_headless` | **PASSED** | 3.01s | - |
| `dynamics_environment_query` | Dynamics Environment Query & 3D Surface Geometry | `python` | **PASSED** | 1.13s | - |
| `contact_dynamics_math` | Contact Dynamics Foundation & Momentum Impulse | `python` | **PASSED** | 1.32s | - |
| `contact_force_solver` | Multi-Contact Force Solver & Constraint Allocation | `python` | **PASSED** | 1.33s | - |
| `forward_dynamics` | Forward Dynamics Single-Step Integration Kernel | `python` | **PASSED** | 1.14s | - |
| `closed_loop_dynamics` | Multi-Frame Dynamics Closed-Loop Control & State Feedback | `python` | **PASSED** | 2.13s | - |
| `runner_unit_tests` | Test Suite Runner Unit Tests | `python` | **PASSED** | 1.87s | - |
| `physics_joint_limits` | Anatomical Joint ROM Limit Verification | `blender_headless` | **PASSED** | 3.1s | - |
| `physics_rigid_link_com` | Rigid Link Segments & Whole-Body CoM | `blender_headless` | **PASSED** | 3.0s | - |
| `mesh_environment_query` | Environment Gate 01: Blender Mesh Environment Adapter & Data Authenticity | `blender_headless` | **PASSED** | 6.24s | - |
| `task7a2_p0_teleport_regression` | Task 7A-2 P0: Detection & Prevention of Frame 226->227 Teleportation Defect | `blender_headless` | **PASSED** | 3.41s | - |
| `task7a2_negative_invariance` | Task 7A-2: Terrain Walk Invariance & Negative Physics Verification | `blender_headless` | **PASSED** | 2.38s | - |
| `environment_gate01_unit3` | Environment Gate 01 / Unit 3: Real Mesh BVH Integration & Counter-Factual Verification | `blender_headless` | **AUTOMATED_PASS** | 23.06s | Visual Inspection Required |
| `environment_gate01_u3_s1` | Environment Gate 01 / Unit 3-S1: Root Forward Motion Continuity Across Alternating Footsteps | `blender_headless` | **AUTOMATED_PASS** | 6.77s | Visual Inspection Required |
| `environment_gate01_u3_s2` | Environment Gate 01 / Unit 3-S2: Swing-to-Stance Landing Continuity Repair | `blender_headless` | **AUTOMATED_PASS** | 7.01s | Visual Inspection Required |
| `environment_gate01_unit4` | Environment Gate 01 / Unit 4: Real Mesh Contact Elevation & Consistency | `blender_headless` | **PASSED** | 2.73s | - |
| `environment_gate01_unit4_closure` | Environment Gate 01 / Unit 4: Non-Support Rejection & Analytical Fallback Closure | `blender_headless` | **PASSED** | 2.83s | - |
| `terrain_planning_contract` | Terrain Planning Joint Repair: Direction, Seam, and Timebase Contracts | `blender_headless` | **PASSED** | 3.27s | - |