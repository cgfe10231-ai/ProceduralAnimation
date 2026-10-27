# Environment Gate 01 — Repair Unit 1: Test Coverage Matrix

Comprehensive validation matrix for all 32 tests implemented in [`tests/test_mesh_environment_query.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_mesh_environment_query.py).

Every test is verified against the 8-field physical contract of `SurfaceQueryResult`:
1. `surface_id`: Unique non-empty surface identifier (`mesh:<object>:<poly_idx>`)
2. `surface_type`: Verified semantic classification enum string
3. `contact_point_world`: Full 3D coordinate vector $(x, y, z)$
4. `surface_normal_world`: Full 3D outward normal vector $(nx, ny, nz)$, verified unit length error $< 10^{-5}$
5. `signed_distance`: Signed geometric distance with sign matching outward normal dot product
6. `allows_regular_support`: Stance support eligibility flag
7. `ray_hit_distance`: Verified against independent Euclidean calculation $\|\mathbf{p}_{\text{hit}} - \mathbf{p}_{\text{orig}}\|$ with ray alignment
8. `source_type`: Data provenance (`mesh` on hit, `none` on miss)

---

## Complete Test Matrix

| # | Test Method Name | Input Geometry | Query Vector / Mode | Expected Hit Object | Surface Type | Contact XYZ (m) | Normal XYZ | Signed Dist (m) | Ray Dist (m) | Support | Source |
|:--|:-----------------|:---------------|:--------------------|:--------------------|:-------------|:----------------|:-----------|:----------------|:-------------|:-------:|:------:|
| **01** | `test_01_read_only_playground_blend_geometry` | Historical Playground `.blend` | $(0, 0, 5) \to (0, 0, -1)$ | `Surface_FlatGround` | `horizontal_ground` | $(0.0, 0.0, 0.0)$ | $(0, 0, 1)$ | $+5.000$ | $5.000$ | True | `mesh` |
| **01b**| (Ramp section in test 01) | Historical Playground `.blend` | $(0, 13.5, 5) \to (0, 0, -1)$ | `Surface_Ramp_Up` | `sloped_ramp` | $(0.0, 13.5, 0.670)$ | $(0, -0.259, 0.966)$ | $+4.182$ | $4.330$ | True | `mesh` |
| **02** | `test_02_dynamic_mesh_translation` | Translated Cube ($+2.5\text{m}$) | $(0, 0, 10) \to (0, 0, -1)$ | `Cube` | `box_top` | $(0.0, 0.0, 4.5)$ | $(0, 0, 1)$ | $+5.500$ | $5.500$ | True | `mesh` |
| **03** | `test_03_dynamic_mesh_rotation` | Rotated Plane ($45^\circ$) | $(0, 0, 5) \to (0, 0, -1)$ | `Plane` | `sloped_ramp` | $(0.0, 0.0, 0.0)$ | $(0, -0.707, 0.707)$ | $+3.536$ | $5.000$ | True | `mesh` |
| **04** | `test_04_vertex_level_mesh_editing` | Edited Mesh Vertices ($+1.5\text{m}$) | Ground query at $(0, 0)$ | `Cube` | `box_top` | $(0.0, 0.0, 3.5)$ | $(0, 0, 1)$ | $+6.500$ | $6.500$ | True | `mesh` |
| **05** | `test_05_object_removal_returns_miss` | Removed Mesh Object | $(0, 0, 5) \to (0, 0, -1)$ | `none` | `none` | $(0.0, 0.0, 0.0)$ | $(0, 0, 1)$ | $+\infty$ | $+\infty$ | False | `none` |
| **06** | `test_06_non_support_surface_discrimination` | Vertical Wall Lateral Face | $(0, 3, 1) \to (0, 1, 0)$ | `Cube` | `vertical_wall` | $(0.0, 4.0, 1.0)$ | $(0, -1, 0)$ | $+1.000$ | $1.000$ | False | `mesh` |
| **07** | `test_07_friction_metadata_differentiation` | Custom Friction ($0.42$) vs Default | Ray query on Cube A / B | `CubeA` / `CubeB` | `box_top` | $(-3.0, 0.0, 2.0)$ | $(0, 0, 1)$ | $+3.000$ | $3.000$ | True | `mesh` |
| **08** | `test_08_dynamics_environment_query_integration` | `DynamicsEnvironmentQuery` delegation | Spatial query at platform | `Cube` | `box_top` | $(0.0, 10.0, 3.0)$ | $(0, 0, 1)$ | $+3.000$ | $3.000$ | True | `mesh` |
| **09** | `test_09_a03_1_collection_does_not_exist` | Mesh in unlinked collection | $(0, 0, 5) \to (0, 0, -1)$ | `none` | `none` | $(0.0, 0.0, 0.0)$ | $(0, 0, 1)$ | $+\infty$ | $+\infty$ | False | `none` |
| **10** | `test_10_a03_2_collection_empty` | Empty target collection | $(0, 0, 5) \to (0, 0, -1)$ | `none` | `none` | $(0.0, 0.0, 0.0)$ | $(0, 0, 1)$ | $+\infty$ | $+\infty$ | False | `none` |
| **11** | `test_11_a03_3_collection_isolation` | Allowed Z=2.0 vs Forbidden Z=4.0 | $(0, 0, 10) \to (0, 0, -1)$ | `Surface_Allowed` | `horizontal_ground` | $(0.0, 0.0, 2.0)$ | $(0, 0, 1)$ | $+8.000$ | $8.000$ | True | `mesh` |
| **12** | `test_12_a03_4_explicit_all_scene_mode` | Two collections in all-scene mode | Raycast to Cube1 and Cube2 | `Cube1` / `Cube2` | `box_top` | $(\pm 5.0, 0.0, 2.0)$ | $(0, 0, 1)$ | $+3.000$ | $3.000$ | True | `mesh` |
| **13** | `test_13_a01_1_ray_unfiltered_nearest` | Box at Z=5.0 obscuring Plane at Z=2.0 | $(0, 0, 8) \to (0, 0, -1)$ | `Box_Front` | `box_top` | $(0.0, 0.0, 5.0)$ | $(0, 0, 1)$ | $+3.000$ | $3.000$ | True | `mesh` |
| **14** | `test_14_a01_2_ray_filtered_finds_second_surface` | Same scene, filter `horizontal_ground` | $(0, 0, 8) \to (0, 0, -1)$ | `Ground_Back` | `horizontal_ground` | $(0.0, 0.0, 2.0)$ | $(0, 0, 1)$ | $+6.000$ | $6.000$ | True | `mesh` |
| **15** | `test_15_a01_3_ray_filtered_nonexistent_type` | Same scene, filter `sloped_ramp` | $(0, 0, 8) \to (0, 0, -1)$ | `none` | `none` | $(0.0, 0.0, 0.0)$ | $(0, 0, 1)$ | $+\infty$ | $+\infty$ | False | `none` |
| **16** | `test_16_a01_4_ray_filtered_insufficient_distance` | Same scene, distance $4\text{m} < 6\text{m}$ | $(0, 0, 8) \to (0, 0, -1)$ | `none` | `none` | $(0.0, 0.0, 0.0)$ | $(0, 0, 1)$ | $+\infty$ | $+\infty$ | False | `none` |
| **17** | `test_17_a01_5_ray_direction_scale_invariance` | Direction $(0,0,-1)$ vs $(0,0,-5)$ | Raycast with scaled vectors | `Ground_Back` | `horizontal_ground` | $(0.0, 0.0, 2.0)$ | $(0, 0, 1)$ | $+6.000$ | $6.000$ | True | `mesh` |
| **18** | `test_18_a01_6_ray_origin_on_surface` | Origin directly on surface | $(0, 0, 2) \to (0, 0, -1)$ | `Ground_Back` | `horizontal_ground` | $(0.0, 0.0, 2.0)$ | $(0, 0, 1)$ | $+0.000$ | $0.000$ | True | `mesh` |
| **19** | `test_19_a02_1_nearest_unfiltered_nearest` | Box at dist 0.2m, Plane at dist 0.8m | Nearest from $(0, 0, 1.0)$ | `Box_Near` | `box_top` | $(0.0, 0.0, 0.8)$ | $(0, 0, 1)$ | $+0.200$ | N/A | True | `mesh` |
| **20** | `test_20_a02_2_nearest_filtered_finds_target_surface` | Same scene, filter `horizontal_ground` | Nearest from $(0, 0, 1.0)$ | `Plane_Far` | `horizontal_ground` | $(0.0, 0.0, 0.2)$ | $(0, 0, 1)$ | $+0.800$ | N/A | True | `mesh` |
| **21** | `test_21_a02_3_nearest_filtered_insufficient_radius` | Same scene, max_distance $0.5\text{m} < 0.8\text{m}$ | Nearest from $(0, 0, 1.0)$ | `none` | `none` | $(0.0, 0.0, 0.0)$ | $(0, 0, 1)$ | $+\infty$ | N/A | False | `none` |
| **22** | `test_22_a02_4_nearest_filtered_moved_query_point` | Query moved to $(0, 0, 0.3)$ | Nearest from $(0, 0, 0.3)$ | `Plane_Far` | `horizontal_ground` | $(0.0, 0.0, 0.2)$ | $(0, 0, 1)$ | $+0.100$ | N/A | True | `mesh` |
| **23** | `test_23_a02_5_nearest_filtered_rotated_surface_normal` | Plane rotated $30^\circ$ around X | Nearest with filter `sloped_ramp` | `Plane_Far` | `sloped_ramp` | Contact on plane | $(0, -0.500, 0.866)$ | Verified | N/A | True | `mesh` |
| **24** | `test_24_non_axis_aligned_rotated_scene` | Plane at $(3,4,2)$, Euler $(30^\circ, 45^\circ, 0^\circ)$ | Ray & Nearest from $(3.5, 4.2, 5.0)$ | `Rotated_Plane` | `sloped_ramp` | $(3.5, 4.2, 1.663)$ | $(0.612, -0.500, 0.612)$ | $+2.043$ | $3.337$ | True | `mesh` |
| **25** | `test_25_t03_single_surface_query` | Ground plane at $(1, 2, 0)$ | $(1, 2, 5) \to (0, 0, -1)$ | `Plane_Ground` | `horizontal_ground` | $(1.0, 2.0, 0.0)$ | $(0, 0, 1)$ | $+5.000$ | $5.000$ | True | `mesh` |
| **26** | `test_26_t03_multi_surface_query` | 3 surfaces: Box (Z=6), Ramp (Z=4), Ground (Z=2) | Filtered for `horizontal_ground` | `Ground_Bottom` | `horizontal_ground` | $(0.0, 0.0, 2.0)$ | $(0, 0, 1)$ | $+8.000$ | $8.000$ | True | `mesh` |
| **27** | `test_27_t03_consecutive_filters` | Same 3 stacked surfaces | Consecutive filters: box, ramp, ground | Respective objects | Respective types | Elevations 6.0, 4.0, 2.0 | Respective normals | Respective dists | Respective dists | True | `mesh` |
| **28** | `test_28_t03_exact_budget_reach` | 4 obstacle planes + 1 target plane | `max_steps=5`, filter `horizontal_ground` | `Ground_Target` | `horizontal_ground` | $(0.0, 0.0, 1.0)$ | $(0, 0, 1)$ | $+7.000$ | $7.000$ | True | `mesh` |
| **29** | `test_29_t03_budget_exhaustion` | 4 obstacle planes + 1 target plane | `max_steps=4`, filter `horizontal_ground` | `none` | `none` | $(0.0, 0.0, 0.0)$ | $(0, 0, 1)$ | $+\infty$ | $+\infty$ | False | `none` |
| **30** | `test_30_t03_ultra_thin_layer` | $50\mu m$ obstacle box at Z=3.0, ground at Z=1.0 | `step_epsilon=1e-6`, filter `horizontal_ground` | `Ground_Target` | `horizontal_ground` | $(0.0, 0.0, 1.0)$ | $(0, 0, 1)$ | $+4.000$ | $4.000$ | True | `mesh` |
| **31** | `test_31_t03_ray_origin_on_surface_boundary` | Origin placed at obstacle top face ($Z=5.0$) | Filter `horizontal_ground` down to Z=2.0 | `Ground_Target` | `horizontal_ground` | $(0.0, 0.0, 2.0)$ | $(0, 0, 1)$ | $+3.000$ | $3.000$ | True | `mesh` |
| **32** | `test_32_t03_distance_almost_exhausted` | Distance $6.0001\text{m}$ vs $5.9990\text{m}$ to Z=2.0 | Boundary distance check | `Ground_Target` (hit) / `none` (miss) | `horizontal_ground` / `none` | $(0.0, 0.0, 2.0)$ / $(0,0,0)$ | $(0, 0, 1)$ | $+6.000$ / $+\infty$ | $6.000$ / $+\infty$ | T / F | `mesh` / `none` |
