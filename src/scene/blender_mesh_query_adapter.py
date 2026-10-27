"""Blender Mesh Environment Query Adapter (Environment Gate 01).

Implements real-geometry environmental perception against evaluated Blender scene meshes:
- Constructs world-space BVH trees (mathutils.bvhtree.BVHTree) from evaluated scene geometry.
- Supports arbitrary object translation, rotation, scaling, and vertex-level edits.
- Eliminates the Dual Source of Truth by treating live Blender meshes as the primary geometric reality.
- Distinguishes walkable support surfaces from vertical walls, steep drops, and empty gaps.
- Accurately tracks surface identification, outward normals, signed distances, ray travel distances,
  and friction metadata (distinguishing actual scene properties from default fallback values).
- Seamlessly integrates with `DynamicsEnvironmentQuery` without modifying human control chains.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import array
import math
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

import bpy
import mathutils
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from src.scene.environment_query import (
    DynamicsEnvironmentQuery,
    SurfaceGeometryType,
    SurfaceQueryResult,
)


@dataclass
class MeshPolygonMetadata:
    """Detailed metadata associated with a single evaluated mesh polygon."""
    object_name: str
    polygon_index: int
    surface_id: str
    surface_type: SurfaceGeometryType
    normal_world: Tuple[float, float, float]
    friction_coeff: float
    has_custom_friction: bool
    allows_regular_support: bool
    material_name: Optional[str] = None


class AdapterCacheState(Enum):
    """Lifecycle states for BlenderMeshEnvironmentAdapter cache."""
    INVALID = "invalid"                    # Uninitialized or explicitly invalidated cache
    VALID_EMPTY = "valid_empty"            # Successfully built, confirmed empty (0 target meshes or 0 polys)
    VALID_NON_EMPTY = "valid_non_empty"    # Successfully built with compiled BVHTree
    REBUILDING = "rebuilding"              # Build currently in progress
    FAILED = "failed"                      # Build failed and rolled back


@dataclass
class ObjectGeometrySnapshot:
    """Cached geometric snapshot of a tracked mesh object for change detection."""
    session_uid: int
    name: str
    matrix_world: Matrix
    mesh_session_uid: int
    vert_count: int
    poly_count: int
    vert_hash: int
    loop_hash: int
    mod_fingerprint: tuple
    custom_props: tuple


class BlenderMeshEnvironmentAdapter:
    """Evaluates real Blender mesh geometry and provides spatial and raycast surface queries.

    Design and Correctness Principles:
    1. World-Space Evaluation:
       Extracts evaluated meshes via `depsgraph = bpy.context.evaluated_depsgraph_get()` and
       transforms all vertices into World Space (`obj.matrix_world @ v.co`). This guarantees
       that parent transforms, constraints, modifiers, translations, rotations, and vertex edits
       are 100% faithfully reflected in query results.
    2. Zero Hallucination:
       If a ray does not intersect any evaluated mesh, query returns `success=False` with
       `error_reason`. It NEVER manufactures a fake horizontal plane at Z=0.0m.
    3. Regular Support Eligibility:
       Surfaces are evaluated for foot support capability. Vertical walls, steep slopes
       (normal.z < min_support_normal_z), and ceilings explicitly set `allows_regular_support=False`.
    4. Cache & Invalidation Rules:
       The spatial BVH tree is cached in memory. Explicit calls to `rebuild()` or `refresh()`
       detect dirty states or force complete re-evaluation from Blender's depsgraph.
    """

    def __init__(
        self,
        scene: Optional[bpy.types.Scene] = None,
        collection_names: Optional[Sequence[str]] = ("Playground_Surfaces",),
        object_names: Optional[Sequence[str]] = None,
        default_friction: float = 0.65,
        min_support_normal_z: float = 0.50,
        step_epsilon: float = 1e-6,
    ) -> None:
        self._scene = scene or bpy.context.scene
        self._collection_names = list(collection_names) if collection_names is not None else None
        self._object_names = set(object_names) if object_names is not None else None
        self._default_friction = float(default_friction)
        self._min_support_normal_z = float(min_support_normal_z)
        self._step_epsilon = float(step_epsilon)

        # Cache lifecycle and state
        self._cache_state: AdapterCacheState = AdapterCacheState.INVALID
        self._rebuild_count: int = 0
        self._cache_version: int = 0
        self._dirty: bool = True
        self._last_refresh_time: float = 0.0

        # Cached spatial data
        self._bvh: Optional[BVHTree] = None
        self._poly_metadata: List[MeshPolygonMetadata] = []
        self._world_vertices: List[Vector] = []
        self._world_polygons: List[List[int]] = []

        # Object tracking and snapshotting
        self._tracked_objects: List[str] = []
        self._tracked_session_uids: Set[int] = set()
        self._tracked_names_by_uid: Dict[int, str] = {}
        self._object_snapshots: Dict[int, ObjectGeometrySnapshot] = {}

        # Build initial cache
        self.rebuild()

    # -------------------------------------------------------------------------
    # Cache Management & Invalidation Rules
    # -------------------------------------------------------------------------

    def invalidate(self) -> None:
        """Mark the adapter cache dirty to trigger re-evaluation upon next query (Path B)."""
        self._dirty = True
        self._cache_state = AdapterCacheState.INVALID

    @staticmethod
    def _compute_vert_hash(mesh: Optional[bpy.types.Mesh]) -> int:
        """Fast hash of raw vertex coordinates using memory buffer."""
        if mesh is None or len(mesh.vertices) == 0:
            return 0
        buf = array.array("f", [0.0]) * (len(mesh.vertices) * 3)
        mesh.vertices.foreach_get("co", buf)
        return hash(buf.tobytes())

    @staticmethod
    def _compute_loop_hash(mesh: Optional[bpy.types.Mesh]) -> int:
        """Fast hash of polygon loop vertex indices for topology detection."""
        if mesh is None or len(mesh.loops) == 0:
            return 0
        buf = array.array("i", [0]) * len(mesh.loops)
        mesh.loops.foreach_get("vertex_index", buf)
        return hash(buf.tobytes())

    @staticmethod
    def _compute_mod_fingerprint(obj: bpy.types.Object) -> tuple:
        """Generic fingerprint of all object modifiers, properties, and viewport visibility."""
        if not obj.modifiers:
            return ()
        mods_data = []
        for m in obj.modifiers:
            props = []
            for p in m.rna_type.properties:
                if not p.is_readonly and p.type in {"INT", "FLOAT", "BOOLEAN", "ENUM", "STRING"}:
                    try:
                        props.append((p.identifier, getattr(m, p.identifier)))
                    except Exception:
                        pass
            mods_data.append((m.name, m.type, m.show_viewport, tuple(props)))
        return tuple(mods_data)

    @staticmethod
    def _matrices_differ(m1: Matrix, m2: Matrix, tol: float = 1e-6) -> bool:
        """Check if two 4x4 transformation matrices differ by more than tolerance."""
        for r in range(4):
            for c in range(4):
                if abs(m1[r][c] - m2[r][c]) > tol:
                    return True
        return False

    def _compute_object_snapshot(self, obj: bpy.types.Object) -> ObjectGeometrySnapshot:
        mesh_uid = obj.data.session_uid if obj.data else 0
        vert_count = len(obj.data.vertices) if obj.data else 0
        poly_count = len(obj.data.polygons) if obj.data else 0
        v_hash = self._compute_vert_hash(obj.data)
        l_hash = self._compute_loop_hash(obj.data)
        m_fp = self._compute_mod_fingerprint(obj)
        custom_props = (obj.get("friction_coeff"), obj.get("allows_regular_support"))
        return ObjectGeometrySnapshot(
            session_uid=obj.session_uid,
            name=obj.name,
            matrix_world=obj.matrix_world.copy(),
            mesh_session_uid=mesh_uid,
            vert_count=vert_count,
            poly_count=poly_count,
            vert_hash=v_hash,
            loop_hash=l_hash,
            mod_fingerprint=m_fp,
            custom_props=custom_props,
        )

    def _check_scene_changed(self) -> bool:
        """Inspect tracked scene objects for transform, geometry, modifier or collection membership changes.

        Returns True if changes require a BVH rebuild, False if cache remains valid.
        Renaming of objects without geometric change is handled in-place with 0 rebuilds.
        """
        target_objects = self._gather_target_objects()
        current_mesh_objects = [
            obj for obj in target_objects if obj.type == "MESH" and obj.data is not None
        ]

        current_uids = {obj.session_uid for obj in current_mesh_objects}

        # 1. Collection membership additions, removals, deletions (Defect C05)
        if current_uids != self._tracked_session_uids:
            return True

        # If both are empty, scene remains cleanly empty (Defect C01)
        if not current_uids:
            return False

        # 2. Inspect each tracked object for transform, geometry, and modifier consistency
        for obj in current_mesh_objects:
            uid = obj.session_uid
            snapshot = self._object_snapshots.get(uid)
            if snapshot is None:
                return True

            # Transform matrix (translation, rotation, non-uniform scale, parent hierarchy) (Defect C02)
            if self._matrices_differ(obj.matrix_world, snapshot.matrix_world):
                return True

            # Data pointer & mesh counts (Defect C03)
            if obj.data.session_uid != snapshot.mesh_session_uid:
                return True
            if len(obj.data.vertices) != snapshot.vert_count or len(obj.data.polygons) != snapshot.poly_count:
                return True

            # Vertex coordinates & loop topology (Path A automatic detection) (Defect C03)
            if self._compute_vert_hash(obj.data) != snapshot.vert_hash:
                return True
            if self._compute_loop_hash(obj.data) != snapshot.loop_hash:
                return True

            # Modifier additions, removals, property adjustments, viewport visibility (Defect C04)
            if self._compute_mod_fingerprint(obj) != snapshot.mod_fingerprint:
                return True

            # Custom object properties (friction, support override)
            curr_custom = (obj.get("friction_coeff"), obj.get("allows_regular_support"))
            if curr_custom != snapshot.custom_props:
                return True

            # Object rename without geometric change: update metadata in-place (0 rebuilds) (Defect C05)
            if obj.name != snapshot.name:
                old_name = snapshot.name
                new_name = obj.name
                for meta in self._poly_metadata:
                    if meta.object_name == old_name:
                        meta.object_name = new_name
                        meta.surface_id = f"mesh:{new_name}:{meta.polygon_index}"
                snapshot.name = new_name
                self._tracked_names_by_uid[uid] = new_name
                self._tracked_objects = [
                    self._tracked_names_by_uid[u] for u in self._tracked_session_uids if u in self._tracked_names_by_uid
                ]

        return False

    def rebuild(self) -> None:
        """Force complete re-evaluation of target scene meshes and rebuild BVH tree."""
        self._cache_state = AdapterCacheState.REBUILDING
        eval_objs_to_clear: List[Tuple[bpy.types.Object, bpy.types.Mesh]] = []

        try:
            target_objects = self._gather_target_objects()

            mesh_objects = [obj for obj in target_objects if obj.type == "MESH" and obj.data is not None]
            if not mesh_objects:
                self._world_vertices = []
                self._world_polygons = []
                self._poly_metadata = []
                self._bvh = None
                self._tracked_objects = []
                self._tracked_session_uids = set()
                self._tracked_names_by_uid = {}
                self._object_snapshots = {}
                self._dirty = False
                self._cache_state = AdapterCacheState.VALID_EMPTY
                self._rebuild_count += 1
                self._cache_version += 1
                self._last_refresh_time = time.time()
                return

            new_world_verts: List[Vector] = []
            new_polys: List[List[int]] = []
            new_poly_meta: List[MeshPolygonMetadata] = []
            new_snapshots: Dict[int, ObjectGeometrySnapshot] = {}
            new_tracked_names: List[str] = []
            new_tracked_uids: Set[int] = set()
            new_names_by_uid: Dict[int, str] = {}
            vert_offset = 0

            depsgraph = bpy.context.evaluated_depsgraph_get()

            for obj in mesh_objects:
                new_tracked_names.append(obj.name)
                new_tracked_uids.add(obj.session_uid)
                new_names_by_uid[obj.session_uid] = obj.name
                new_snapshots[obj.session_uid] = self._compute_object_snapshot(obj)

                eval_obj = obj.evaluated_get(depsgraph)
                mesh = eval_obj.to_mesh()
                eval_objs_to_clear.append((eval_obj, mesh))
                mat = obj.matrix_world

                # Extract world-space vertices
                for v in mesh.vertices:
                    new_world_verts.append(mat @ v.co)

                # Extract friction metadata from object or active material
                has_custom_friction = False
                friction_coeff = self._default_friction
                if "friction_coeff" in obj:
                    try:
                        friction_coeff = float(obj["friction_coeff"])
                        has_custom_friction = True
                    except (ValueError, TypeError):
                        pass
                elif mesh.materials:
                    first_mat = mesh.materials[0]
                    if first_mat and "friction_coeff" in first_mat:
                        try:
                            friction_coeff = float(first_mat["friction_coeff"])
                            has_custom_friction = True
                        except (ValueError, TypeError):
                            pass

                explicit_support = obj.get("allows_regular_support")

                # Process polygons
                for p in mesh.polygons:
                    new_polys.append([idx + vert_offset for idx in p.vertices])

                    if len(p.vertices) >= 3:
                        v0 = new_world_verts[vert_offset + p.vertices[0]]
                        v1 = new_world_verts[vert_offset + p.vertices[1]]
                        v2 = new_world_verts[vert_offset + p.vertices[2]]
                        e1 = v1 - v0
                        e2 = v2 - v0
                        raw_norm = e1.cross(e2)
                        norm_len = raw_norm.length
                        if norm_len > 1e-8:
                            norm_world = (raw_norm.x / norm_len, raw_norm.y / norm_len, raw_norm.z / norm_len)
                        else:
                            norm_world = (0.0, 0.0, 1.0)
                    else:
                        norm_world = (0.0, 0.0, 1.0)

                    surf_type = self._classify_surface_type(obj.name, norm_world)
                    if explicit_support is not None:
                        allows_support = bool(explicit_support)
                    else:
                        allows_support = norm_world[2] >= self._min_support_normal_z

                    mat_name = (
                        mesh.materials[p.material_index].name
                        if mesh.materials and p.material_index < len(mesh.materials) and mesh.materials[p.material_index]
                        else None
                    )

                    new_poly_meta.append(
                        MeshPolygonMetadata(
                            object_name=obj.name,
                            polygon_index=p.index,
                            surface_id=f"mesh:{obj.name}:{p.index}",
                            surface_type=surf_type,
                            normal_world=norm_world,
                            friction_coeff=friction_coeff,
                            has_custom_friction=has_custom_friction,
                            allows_regular_support=allows_support,
                            material_name=mat_name,
                        )
                    )

                vert_offset += len(mesh.vertices)

            # Build BVH tree
            if new_polys:
                new_bvh = BVHTree.FromPolygons(new_world_verts, new_polys)
                target_state = AdapterCacheState.VALID_NON_EMPTY
            else:
                new_bvh = None
                target_state = AdapterCacheState.VALID_EMPTY

            # Atomic commit: all state published simultaneously
            self._world_vertices = new_world_verts
            self._world_polygons = new_polys
            self._poly_metadata = new_poly_meta
            self._bvh = new_bvh
            self._tracked_objects = new_tracked_names
            self._tracked_session_uids = new_tracked_uids
            self._tracked_names_by_uid = new_names_by_uid
            self._object_snapshots = new_snapshots
            self._dirty = False
            self._cache_state = target_state
            self._rebuild_count += 1
            self._cache_version += 1
            self._last_refresh_time = time.time()

        except Exception as e:
            self._cache_state = AdapterCacheState.FAILED
            self._dirty = True
            raise e
        finally:
            for eval_obj, mesh in eval_objs_to_clear:
                try:
                    eval_obj.to_mesh_clear()
                except Exception:
                    pass

    def refresh(self, force: bool = False) -> None:
        """Check if scene geometry or transforms changed, and rebuild BVH if dirty."""
        if (
            force
            or self._dirty
            or self._cache_state in (AdapterCacheState.INVALID, AdapterCacheState.FAILED)
        ):
            self.rebuild()
            return

        if self._check_scene_changed():
            self.rebuild()

    def _gather_target_objects(self) -> List[bpy.types.Object]:
        """Collect mesh objects from configured collections, object names, or active scene.

        Strict Candidate Isolation Contract (Repair Unit 1 / Defect A03):
        - Rule A: Explicit Collection Mode (`collection_names is not None`):
          Queries meshes strictly contained within specified collections (retaining subcollection
          traversal). Never automatically includes other collections or falls back to full scene
          scan, even if the collection is non-existent or contains 0 meshes (returns empty list).
        - Rule B: Explicit Object Mode (`object_names is not None`):
          Queries specified mesh object names only. Non-existent or non-mesh names are ignored;
          duplicates are deduplicated; never falls back to full scene scan.
        - Rule C: Full Scene Mode:
          Permitted ONLY when caller explicitly sets `collection_names=None` AND `object_names=None`.
          Full scene scanning is never used as an implicit fallback.
        """
        objects: List[bpy.types.Object] = []

        if self._object_names is not None:
            for name in self._object_names:
                obj = bpy.data.objects.get(name)
                if obj and obj.type == "MESH" and obj not in objects:
                    objects.append(obj)
            return objects

        if self._collection_names is not None:
            for col_name in self._collection_names:
                col = bpy.data.collections.get(col_name)
                if col:
                    for obj in col.all_objects:
                        if obj.type == "MESH" and obj not in objects:
                            objects.append(obj)
            return objects

        # Rule C: Explicit full-scene mode (both collection_names and object_names are None)
        for obj in self._scene.objects:
            if obj.type == "MESH" and obj not in objects:
                objects.append(obj)
        return objects

    def _classify_surface_type(
        self,
        object_name: str,
        normal_world: Tuple[float, float, float],
    ) -> SurfaceGeometryType:
        """Heuristically classify surface geometry based on normal and naming cues."""
        name_lower = object_name.lower()
        nz = normal_world[2]

        if nz >= 0.99:
            if "stair" in name_lower:
                return SurfaceGeometryType.STAIR_TREAD
            if "box" in name_lower or "vault" in name_lower or "platform" in name_lower or "bridge" in name_lower:
                return SurfaceGeometryType.BOX_TOP
            return SurfaceGeometryType.HORIZONTAL_GROUND

        if 0.15 <= nz < 0.99:
            return SurfaceGeometryType.SLOPED_RAMP

        if -0.15 < nz < 0.15:
            if "stair" in name_lower:
                return SurfaceGeometryType.STAIR_RISER
            if "box" in name_lower or "vault" in name_lower:
                return SurfaceGeometryType.BOX_SIDE
            return SurfaceGeometryType.VERTICAL_WALL

        return SurfaceGeometryType.VERTICAL_WALL

    # -------------------------------------------------------------------------
    # Spatial & Ray Query Interfaces
    # -------------------------------------------------------------------------

    def ray_cast(
        self,
        origin: Tuple[float, float, float],
        direction: Tuple[float, float, float],
        distance: float = 10.0,
        surface_type_filter: Optional[str] = None,
        max_steps: int = 64,
        step_epsilon: Optional[float] = None,
    ) -> SurfaceQueryResult:
        """Cast a directional ray into the evaluated mesh BVH tree.

        Semantics (Repair Unit 1 / Defect A01):
        - Unfiltered (`surface_type_filter is None`):
          Returns the nearest physical hit along the ray path. Never penetrates or searches behind.
        - Filtered (`surface_type_filter is not None`):
          Searches forward along ray path up to `distance` for the closest surface matching filter.
          NOTE: This is a geometric query and does not imply human penetration feasibility.
        - Failure Classification (T03):
          Distinguishes between NO_HIT (search completed up to distance without match) and
          SEARCH_LIMIT_REACHED (iteration budget exhausted before reaching distance).
        """
        self.refresh()

        if self._bvh is None or not self._poly_metadata:
            return SurfaceQueryResult(
                surface_id="none",
                surface_type="none",
                contact_point_world=(0.0, 0.0, 0.0),
                surface_normal_world=(0.0, 0.0, 1.0),
                signed_distance=float("inf"),
                friction_coeff=0.0,
                allows_regular_support=False,
                success=False,
                ray_hit_distance=float("inf"),
                error_reason="NO_HIT: No evaluated meshes available in environment adapter",
                source_type="none",
            )

        rx, ry, rz = direction
        r_len = math.sqrt(rx * rx + ry * ry + rz * rz)
        if r_len < 1e-8:
            return self.find_nearest(origin, max_distance=distance, surface_type_filter=surface_type_filter)

        dir_vec = Vector((rx / r_len, ry / r_len, rz / r_len))
        orig_vec = Vector(origin)

        # Standard unfiltered query: strictly return the first physical surface hit
        if not surface_type_filter:
            hit_loc, hit_norm, hit_idx, hit_dist = self._bvh.ray_cast(orig_vec, dir_vec, distance)

            if hit_loc is None or hit_idx is None:
                return SurfaceQueryResult(
                    surface_id="none",
                    surface_type="none",
                    contact_point_world=(0.0, 0.0, 0.0),
                    surface_normal_world=(0.0, 0.0, 1.0),
                    signed_distance=float("inf"),
                    friction_coeff=0.0,
                    allows_regular_support=False,
                    success=False,
                    ray_hit_distance=float("inf"),
                    error_reason=f"NO_HIT: No mesh surface intersected along ray within {distance:.2f}m",
                    source_type="none",
                )

            meta = self._poly_metadata[hit_idx]
            norm_unit = hit_norm.normalized() if hit_norm.length > 1e-8 else Vector(meta.normal_world)
            signed_dist = float((orig_vec - hit_loc).dot(norm_unit))

            return SurfaceQueryResult(
                surface_id=meta.surface_id,
                surface_type=meta.surface_type.value,
                contact_point_world=(float(hit_loc.x), float(hit_loc.y), float(hit_loc.z)),
                surface_normal_world=(float(norm_unit.x), float(norm_unit.y), float(norm_unit.z)),
                signed_distance=signed_dist,
                friction_coeff=meta.friction_coeff,
                allows_regular_support=meta.allows_regular_support,
                success=True,
                ray_hit_distance=float(hit_dist),
                error_reason=None,
                source_type="mesh",
            )

        # Filtered query: search forward along ray direction for closest matching surface
        filter_str = surface_type_filter.value if hasattr(surface_type_filter, "value") else str(surface_type_filter)
        current_origin = orig_vec.copy()
        budget_exhausted = False
        last_hit_idx = None
        current_epsilon = self._step_epsilon if step_epsilon is None else float(step_epsilon)

        found_hit = False
        target_loc = None
        target_norm = None
        target_idx = None
        target_dist = 0.0

        for step_i in range(max_steps):
            dist_from_orig = float((current_origin - orig_vec).dot(dir_vec))
            remaining_dist = distance - dist_from_orig
            if remaining_dist <= 1e-7:
                break

            hit_loc, hit_norm, hit_idx, hit_dist = self._bvh.ray_cast(
                current_origin, dir_vec, remaining_dist
            )

            if hit_loc is None or hit_idx is None:
                break

            # Handle numerical re-hit on exact same polygon
            if hit_idx == last_hit_idx and hit_dist < 1e-6:
                current_epsilon = max(current_epsilon * 2.0, 1e-5)
                current_origin = current_origin + dir_vec * current_epsilon
                continue

            last_hit_idx = hit_idx
            current_epsilon = self._step_epsilon if step_epsilon is None else float(step_epsilon)

            cum_dist = float((hit_loc - orig_vec).dot(dir_vec))
            if cum_dist > distance + 1e-6:
                break

            meta = self._poly_metadata[hit_idx]
            if meta.surface_type.value == filter_str:
                found_hit = True
                target_loc = hit_loc
                target_norm = hit_norm
                target_idx = hit_idx
                target_dist = max(0.0, cum_dist)
                break

            # If this was the last iteration step and we haven't found target, budget is exhausted
            if step_i == max_steps - 1:
                budget_exhausted = True
                break

            # Strictly advance forward past current intersection
            forward_from_hit = hit_loc + dir_vec * current_epsilon
            if (forward_from_hit - current_origin).dot(dir_vec) < current_epsilon:
                current_origin = current_origin + dir_vec * current_epsilon
            else:
                current_origin = forward_from_hit

        if not found_hit or target_loc is None or target_idx is None:
            if budget_exhausted:
                err = f"SEARCH_LIMIT_REACHED: Exceeded maximum ray iteration budget ({max_steps} steps) while searching for filter '{filter_str}' within {distance:.2f}m"
            else:
                err = f"NO_HIT: No mesh surface matching filter '{filter_str}' intersected along ray within {distance:.2f}m"
            return SurfaceQueryResult(
                surface_id="none",
                surface_type="none",
                contact_point_world=(0.0, 0.0, 0.0),
                surface_normal_world=(0.0, 0.0, 1.0),
                signed_distance=float("inf"),
                friction_coeff=0.0,
                allows_regular_support=False,
                success=False,
                ray_hit_distance=float("inf"),
                error_reason=err,
                source_type="none",
            )

        meta = self._poly_metadata[target_idx]
        norm_unit = target_norm.normalized() if target_norm.length > 1e-8 else Vector(meta.normal_world)
        signed_dist = float((orig_vec - target_loc).dot(norm_unit))

        return SurfaceQueryResult(
            surface_id=meta.surface_id,
            surface_type=meta.surface_type.value,
            contact_point_world=(float(target_loc.x), float(target_loc.y), float(target_loc.z)),
            surface_normal_world=(float(norm_unit.x), float(norm_unit.y), float(norm_unit.z)),
            signed_distance=signed_dist,
            friction_coeff=meta.friction_coeff,
            allows_regular_support=meta.allows_regular_support,
            success=True,
            ray_hit_distance=float(target_dist),
            error_reason=None,
            source_type="mesh",
        )

    def find_nearest(
        self,
        point_world: Tuple[float, float, float],
        max_distance: float = 5.0,
        surface_type_filter: Optional[str] = None,
    ) -> SurfaceQueryResult:
        """Find the closest point on evaluated meshes to a 3D query point.

        Semantics (Repair Unit 1 / Defect A02):
        - Unfiltered (`surface_type_filter is None`):
          Returns the globally nearest mesh surface within `max_distance`.
        - Filtered (`surface_type_filter is not None`):
          Returns the nearest matching surface within `max_distance` via BVH range search.
        """
        self.refresh()

        if self._bvh is None or not self._poly_metadata:
            return SurfaceQueryResult(
                surface_id="none",
                surface_type="none",
                contact_point_world=(0.0, 0.0, 0.0),
                surface_normal_world=(0.0, 0.0, 1.0),
                signed_distance=float("inf"),
                friction_coeff=0.0,
                allows_regular_support=False,
                success=False,
                ray_hit_distance=None,
                error_reason="NO_HIT: No evaluated meshes available in environment adapter",
                source_type="none",
            )

        p_vec = Vector(point_world)

        # Unfiltered: globally nearest point
        if not surface_type_filter:
            near_loc, near_norm, near_idx, near_dist = self._bvh.find_nearest(p_vec, max_distance)

            if near_loc is None or near_idx is None:
                return SurfaceQueryResult(
                    surface_id="none",
                    surface_type="none",
                    contact_point_world=(0.0, 0.0, 0.0),
                    surface_normal_world=(0.0, 0.0, 1.0),
                    signed_distance=float("inf"),
                    friction_coeff=0.0,
                    allows_regular_support=False,
                    success=False,
                    ray_hit_distance=None,
                    error_reason=f"NO_HIT: No mesh surface found within max_distance={max_distance:.2f}m",
                    source_type="none",
                )

            meta = self._poly_metadata[near_idx]
            norm_unit = near_norm.normalized() if near_norm.length > 1e-8 else Vector(meta.normal_world)
            diff = p_vec - near_loc
            signed_dist = float(near_dist if diff.dot(norm_unit) >= 0.0 else -near_dist)

            return SurfaceQueryResult(
                surface_id=meta.surface_id,
                surface_type=meta.surface_type.value,
                contact_point_world=(float(near_loc.x), float(near_loc.y), float(near_loc.z)),
                surface_normal_world=(float(norm_unit.x), float(norm_unit.y), float(norm_unit.z)),
                signed_distance=signed_dist,
                friction_coeff=meta.friction_coeff,
                allows_regular_support=meta.allows_regular_support,
                success=True,
                ray_hit_distance=None,
                error_reason=None,
                source_type="mesh",
            )

        # Filtered: find all polygons within max_distance and select closest of matching type
        filter_str = surface_type_filter.value if hasattr(surface_type_filter, "value") else str(surface_type_filter)
        candidates = self._bvh.find_nearest_range(p_vec, max_distance)

        if not candidates:
            return SurfaceQueryResult(
                surface_id="none",
                surface_type="none",
                contact_point_world=(0.0, 0.0, 0.0),
                surface_normal_world=(0.0, 0.0, 1.0),
                signed_distance=float("inf"),
                friction_coeff=0.0,
                allows_regular_support=False,
                success=False,
                ray_hit_distance=None,
                error_reason=f"NO_HIT: No mesh surface found within max_distance={max_distance:.2f}m",
                source_type="none",
            )

        matching = [
            c for c in candidates
            if self._poly_metadata[c[2]].surface_type.value == filter_str
        ]

        if not matching:
            return SurfaceQueryResult(
                surface_id="none",
                surface_type="none",
                contact_point_world=(0.0, 0.0, 0.0),
                surface_normal_world=(0.0, 0.0, 1.0),
                signed_distance=float("inf"),
                friction_coeff=0.0,
                allows_regular_support=False,
                success=False,
                ray_hit_distance=None,
                error_reason=f"NO_HIT: No mesh surface matching filter '{filter_str}' found within max_distance={max_distance:.2f}m",
                source_type="none",
            )

        near_loc, near_norm, near_idx, near_dist = min(matching, key=lambda c: c[3])
        meta = self._poly_metadata[near_idx]
        norm_unit = near_norm.normalized() if near_norm.length > 1e-8 else Vector(meta.normal_world)
        diff = p_vec - near_loc
        signed_dist = float(near_dist if diff.dot(norm_unit) >= 0.0 else -near_dist)

        return SurfaceQueryResult(
            surface_id=meta.surface_id,
            surface_type=meta.surface_type.value,
            contact_point_world=(float(near_loc.x), float(near_loc.y), float(near_loc.z)),
            surface_normal_world=(float(norm_unit.x), float(norm_unit.y), float(norm_unit.z)),
            signed_distance=signed_dist,
            friction_coeff=meta.friction_coeff,
            allows_regular_support=meta.allows_regular_support,
            success=True,
            ray_hit_distance=None,
            error_reason=None,
            source_type="mesh",
        )

    def query_spatial_surface(
        self,
        point_world: Tuple[float, float, float],
        ray_direction: Optional[Tuple[float, float, float]] = None,
        max_distance: float = 10.0,
        surface_type_filter: Optional[str] = None,
    ) -> SurfaceQueryResult:
        """Route spatial query to raycast if direction given, or nearest-point search if None."""
        if ray_direction is not None:
            return self.ray_cast(
                origin=point_world,
                direction=ray_direction,
                distance=max_distance,
                surface_type_filter=surface_type_filter,
            )
        return self.find_nearest(
            point_world=point_world,
            max_distance=max_distance,
            surface_type_filter=surface_type_filter,
        )

    def query_surface_at_point(
        self,
        point_world: Tuple[float, float, float],
        max_distance: float = 5.0,
        surface_type_filter: Optional[str] = None,
    ) -> SurfaceQueryResult:
        """Find nearest surface to a 3D point in world space."""
        return self.find_nearest(
            point_world=point_world,
            max_distance=max_distance,
            surface_type_filter=surface_type_filter,
        )

    # -------------------------------------------------------------------------
    # Backward-Compatible 2.5D Height & Normal Queries
    # -------------------------------------------------------------------------

    def ground_height_at(
        self,
        x: float,
        y: float,
        start_z: float = 50.0,
        max_fall: float = 100.0,
    ) -> Optional[float]:
        """Cast a downward ray from (x, y, start_z) to find true ground Z elevation.

        Returns None if no walkable surface is intersected along the ray.
        """
        res = self.ray_cast(
            origin=(x, y, start_z),
            direction=(0.0, 0.0, -1.0),
            distance=max_fall,
        )
        if res.success and res.allows_regular_support:
            return res.contact_point_world[2]
        return None

    def surface_normal_at(
        self,
        x: float,
        y: float,
        start_z: float = 50.0,
        max_fall: float = 100.0,
    ) -> Optional[Tuple[float, float, float]]:
        """Cast a downward ray from (x, y, start_z) to find surface normal."""
        res = self.ray_cast(
            origin=(x, y, start_z),
            direction=(0.0, 0.0, -1.0),
            distance=max_fall,
        )
        if res.success:
            return res.surface_normal_world
        return None

    # -------------------------------------------------------------------------
    # Introspection & Telemetry
    # -------------------------------------------------------------------------

    @property
    def cache_state(self) -> AdapterCacheState:
        return self._cache_state

    @property
    def rebuild_count(self) -> int:
        return self._rebuild_count

    @property
    def cache_version(self) -> int:
        return self._cache_version

    @property
    def is_empty(self) -> bool:
        return self._cache_state == AdapterCacheState.VALID_EMPTY or len(self._poly_metadata) == 0

    @property
    def has_bvh(self) -> bool:
        return self._bvh is not None

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def tracked_objects(self) -> List[str]:
        return list(self._tracked_objects)

    @property
    def polygon_count(self) -> int:
        return len(self._poly_metadata)

    @property
    def vertex_count(self) -> int:
        return len(self._world_vertices)


def create_mesh_backed_dynamics_query(
    scene: Optional[bpy.types.Scene] = None,
    collection_names: Optional[Sequence[str]] = ("Playground_Surfaces",),
    prefer_mesh: bool = True,
    ground_z: float = 0.0,
) -> DynamicsEnvironmentQuery:
    """Convenience factory: instantiate a DynamicsEnvironmentQuery backed by live Blender meshes."""
    adapter = BlenderMeshEnvironmentAdapter(
        scene=scene,
        collection_names=collection_names,
    )
    query = DynamicsEnvironmentQuery(ground_z=ground_z)
    query.set_mesh_adapter(adapter, prefer_mesh=prefer_mesh)
    return query
