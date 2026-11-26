# ProceduralAnimation Test Execution Report

> **Execution Date**: 2026-11-09 18:43:56  
> **Target Tier**: `motion`  
> **Overall Result**: **ALL PASSED**  
> **Execution Summary**: Total Planned: 12 | Executed: 12 | Passed: 12 (Automated Pass: 6) | Failed: 0 | Skipped: 0 (Req: 0, Opt: 0) | Not Run: 0 | Duration: 52.37s

---

## Test Results Table

| Test ID | Test Name | Runner | Status | Duration | Failure / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `motion_walk_r3b2` | StartStopWalkAction Unified Bridge Regression | `blender_headless` | **PASSED** | 6.06s | - |
| `motion_run_r3b2` | RunAction Unified Bridge Regression | `blender_headless` | **PASSED** | 3.88s | - |
| `motion_sprint_start_r3b2` | SprintStartAction Unified Bridge Regression | `blender_headless` | **PASSED** | 4.67s | - |
| `motion_sprint_brake_r3b2` | SprintBrakeAction Unified Bridge Regression | `blender_headless` | **PASSED** | 2.68s | - |
| `integration_unified_motion` | Unified 462-Frame Motion Pipeline Artifact Verification | `blender_headless` | **AUTOMATED_PASS** | 1.59s | Visual Inspection Required |
| `task7a1_character_playground` | Task 7A-1: 19-Bone Character Integration into DynamicsPlayground & Control Loop | `blender_headless` | **AUTOMATED_PASS** | 2.84s | Visual Inspection Required |
| `task7a2_p0_teleport_regression` | Task 7A-2 P0: Detection & Prevention of Frame 226->227 Teleportation Defect | `blender_headless` | **PASSED** | 2.25s | - |
| `task7a2_terrain_traversal` | Task 7A-2: 19-Bone Character Continuous Terrain Traversal in DynamicsPlayground | `blender_headless` | **AUTOMATED_PASS** | 2.62s | Visual Inspection Required |
| `environment_gate01_unit3` | Environment Gate 01 / Unit 3: Real Mesh BVH Integration & Counter-Factual Verification | `blender_headless` | **AUTOMATED_PASS** | 14.3s | Visual Inspection Required |
| `environment_gate01_u3_s1` | Environment Gate 01 / Unit 3-S1: Root Forward Motion Continuity Across Alternating Footsteps | `blender_headless` | **AUTOMATED_PASS** | 4.56s | Visual Inspection Required |
| `environment_gate01_u3_s2` | Environment Gate 01 / Unit 3-S2: Swing-to-Stance Landing Continuity Repair | `blender_headless` | **AUTOMATED_PASS** | 4.56s | Visual Inspection Required |
| `terrain_planning_contract` | Terrain Planning Joint Repair: Direction, Seam, and Timebase Contracts | `blender_headless` | **PASSED** | 2.36s | - |