"""Unified Dynamics Environment Query and Surface Geometry System (Task 6G-D-PRE-P2).

Provides closed-form, mathematically rigorous 3D environmental surface queries:
- Distinguishes between flat ground, stair treads, stair risers, sloped ramps, vertical walls,
  vault platforms, and ledge bars.
- Supports both 2.5D height-field queries (`ground_height_at`, `surface_normal_at`)
  and full 3D spatial queries (`query_surface_at_point`, `query_spatial_surface`).
- Computes exact surface projection points, unit outward surface normals, signed distances
  (gap > 0, penetration < 0), friction coefficients, and regular support eligibility.
- Backward-compatible with `src.motion.framework.EnvironmentQuery`.
- Pure Python implementation (decoupled from bpy) for lightning-fast unit verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


# =============================================================================
# 1. Enums and Data Contracts
# =============================================================================

class SurfaceGeometryType(str, Enum):
    """Categorical geometry classification of an environmental surface."""
    HORIZONTAL_GROUND = "horizontal_ground"  # Flat ground plane
    STAIR_TREAD = "stair_tread"              # Horizontal walkable step surface
    STAIR_RISER = "stair_riser"              # Vertical step rise (wall-like)
    SLOPED_RAMP = "sloped_ramp"              # Inclined planar surface (up/downhill)
    VERTICAL_WALL = "vertical_wall"          # Vertical wall or obstacle front/side
    BOX_TOP = "box_top"                      # Horizontal elevated platform/table top
    BOX_SIDE = "box_side"                    # Vertical side of an obstacle box
    LEDGE_BAR = "ledge_bar"                  # Overhead horizontal grab bar/ledge


@dataclass
class SurfaceQueryResult:
    """Standardized output structure for environmental surface queries.

    Attributes:
        surface_id: Unique string identifier of the queried surface ('none' if not found).
        surface_type: Categorical string identifier from SurfaceGeometryType.
        contact_point_world: Projected contact point coordinates (x, y, z) in meters.
        surface_normal_world: Unit outward surface normal vector (nx, ny, nz).
        signed_distance: Strictly signed distance relative to surface outward normal.
            > 0: query point is in outward free space (gap).
            0.0: query point is exactly on the surface plane.
            < 0: query point is in inward half-space (penetration).
        friction_coeff: Static friction coefficient of the surface (0.0 if not found).
        allows_regular_support: True if eligible for foot weight support; False for walls/ledges.
        success: True if a matching surface was identified within max_distance; False otherwise.
        ray_hit_distance: Non-negative Euclidean distance traveled along ray to reach intersection
            (>= 0.0 in meters). Evaluates to None for closest-point / spatial non-ray queries.
        error_reason: Human-readable diagnostic description when success is False (None on success).
    """
    surface_id: str
    surface_type: str                   # From SurfaceGeometryType
    contact_point_world: Tuple[float, float, float]
    surface_normal_world: Tuple[float, float, float]
    signed_distance: float              # >0: gap (outside), 0.0: on surface, <0: penetration (inside)
    friction_coeff: float               # Static friction coefficient (e.g. 0.60..0.70)
    allows_regular_support: bool        # True if human foot can stand; False for vertical walls
    success: bool                       # True if a valid surface was found within range
    ray_hit_distance: Optional[float] = None  # Non-negative Euclidean hit distance along ray; None if point query
    error_reason: Optional[str] = None
    source_type: str = "analytical"           # "mesh" | "analytical" | "default" | "none"


# =============================================================================
# 2. Mathematical Oriented Bounded Surface Representation
# =============================================================================

@dataclass
class OrientedSurface:
    """Analytical planar rectangular surface patch bounded in 3D space.

    Coordinate system:
    - `center`: 3D World coordinates of the rectangle center (m).
    - `normal`: Outward unit normal vector pointing into free space.
    - `u_axis`: In-plane unit tangent vector (e.g. Width direction).
    - `v_axis`: In-plane unit tangent vector (e.g. Length direction), such that u x v = normal.
    - `half_extents`: (half_width_u, half_length_v) in meters.
    - `surface_id`: Unique identifier (e.g. 'flat_ground', 'stair_step_01', 'vertical_wall_front').
    - `surface_type`: Classification enum value.
    - `friction_coeff`: Surface friction coefficient.
    - `allows_regular_support`: Whether this surface allows vertical/normal foot support.
    """
    surface_id: str
    surface_type: SurfaceGeometryType
    center: Tuple[float, float, float]
    normal: Tuple[float, float, float]
    u_axis: Tuple[float, float, float]
    v_axis: Tuple[float, float, float]
    half_extents: Tuple[float, float]
    friction_coeff: float = 0.65
    allows_regular_support: bool = True
    description: str = ""

    def __post_init__(self):
        # Normalize vectors and guarantee orthogonality
        nx, ny, nz = self.normal
        n_len = math.sqrt(nx * nx + ny * ny + nz * nz)
        if n_len < 1e-8:
            raise ValueError(f"Degenerate normal for surface {self.surface_id}")
        self.normal = (nx / n_len, ny / n_len, nz / n_len)

        ux, uy, uz = self.u_axis
        u_len = math.sqrt(ux * ux + uy * uy + uz * uz)
        if u_len < 1e-8:
            raise ValueError(f"Degenerate u_axis for surface {self.surface_id}")
        self.u_axis = (ux / u_len, uy / u_len, uz / u_len)

        vx, vy, vz = self.v_axis
        v_len = math.sqrt(vx * vx + vy * vy + vz * vz)
        if v_len < 1e-8:
            raise ValueError(f"Degenerate v_axis for surface {self.surface_id}")
        self.v_axis = (vx / v_len, vy / v_len, vz / v_len)

    def query_closest_point(
        self,
        px: float,
        py: float,
        pz: float,
    ) -> Tuple[Tuple[float, float, float], float, Tuple[float, float, float]]:
        """Calculate closest point on this bounded patch, signed distance, and outward normal.

        Returns:
            (closest_point_world, signed_distance, normal_world)
            signed_distance: positive for points in outward half-space (gap),
                             negative for points in inward half-space (penetration).
        """
        cx, cy, cz = self.center
        dx = px - cx
        dy = py - cy
        dz = pz - cz

        # Project relative vector onto local basis (u, v, normal)
        ux, uy, uz = self.u_axis
        vx, vy, vz = self.v_axis
        nx, ny, nz = self.normal

        u = dx * ux + dy * uy + dz * uz
        v = dx * vx + dy * vy + dz * vz
        w = dx * nx + dy * ny + dz * nz  # Distance along normal

        hu, hv = self.half_extents

        # Clamp (u, v) to rectangular patch boundaries
        u_clamped = max(-hu, min(hu, u))
        v_clamped = max(-hv, min(hv, v))

        # Reconstruct closest point on patch in world coordinates
        proj_x = cx + u_clamped * ux + v_clamped * vx
        proj_y = cy + u_clamped * uy + v_clamped * vy
        proj_z = cz + u_clamped * uz + v_clamped * vz

        # Boundary delta
        du = u - u_clamped
        dv = v - v_clamped

        # If point is directly above/below the patch rectangle
        if abs(du) < 1e-9 and abs(dv) < 1e-9:
            signed_dist = w
        else:
            # Outside rectangular perimeter: compute Euclidean distance, preserve sign of w
            edge_dist = math.sqrt(du * du + dv * dv)
            total_dist = math.sqrt(edge_dist * edge_dist + w * w)
            signed_dist = total_dist if w >= 0.0 else -total_dist

        return (proj_x, proj_y, proj_z), signed_dist, self.normal

    def contains_xy(self, x: float, y: float, tolerance: float = 1e-4) -> bool:
        """Check if 2D coordinates (x, y) fall within this surface's horizontal footprint."""
        # For a horizontal or sloped surface, test if there exists a valid point on the patch
        # corresponding to (x, y).
        cx, cy, cz = self.center
        dx = x - cx
        dy = y - cy

        # For horizontal or moderately sloped surfaces:
        # Solve for local coordinates u, v such that:
        # x = cx + u * ux + v * vx
        # y = cy + u * uy + v * vy
        ux, uy, _ = self.u_axis
        vx, vy, _ = self.v_axis

        det = ux * vy - uy * vx
        if abs(det) < 1e-6:
            # Degenerate horizontal projection (e.g. perfectly vertical wall along ray)
            return False

        u = (dx * vy - dy * vx) / det
        v = (ux * dy - uy * dx) / det

        hu, hv = self.half_extents
        return (-hu - tolerance) <= u <= (hu + tolerance) and (-hv - tolerance) <= v <= (hv + tolerance)

    def elevation_at_xy(self, x: float, y: float) -> Optional[float]:
        """Compute surface Z elevation at (x, y) if within footprint; None if not."""
        if not self.contains_xy(x, y):
            return None

        cx, cy, cz = self.center
        nx, ny, nz = self.normal

        # Check if normal has non-zero Z component
        if abs(nz) < 1e-6:
            # Pure vertical wall has no unique Z for a given (x, y)
            return None

        # Plane equation: nx*(x-cx) + ny*(y-cy) + nz*(z-cz) = 0
        # z = cz - (nx*(x-cx) + ny*(y-cy)) / nz
        z = cz - (nx * (x - cx) + ny * (y - cy)) / nz
        return z


# =============================================================================
# 3. Environment Query Engine Classes
# =============================================================================

class EnvironmentQuery:
    """Base lightweight environment geometry query interface.

    Defaults to a flat ground plane at `Z = 0.0 m` with normal `(0, 0, 1)`.
    Provides default 2.5D height-field and 3D spatial query implementations.
    """

    def __init__(self, ground_z: float = 0.0) -> None:
        self.ground_z = float(ground_z)

    def ground_height_at(self, x: float, y: float) -> float:
        """Return ground surface Z elevation (m) at World `(x, y)`."""
        _ = (x, y)
        return self.ground_z

    def surface_normal_at(self, x: float, y: float) -> Tuple[float, float, float]:
        """Return unit surface normal vector in World Space at `(x, y)`."""
        _ = (x, y)
        return (0.0, 0.0, 1.0)

    def query_surface_at_point(
        self,
        point_world: Tuple[float, float, float],
        max_distance: float = 5.0,
        surface_type_filter: Optional[str] = None,
    ) -> SurfaceQueryResult:
        """Baseline 3D query against the infinite ground plane."""
        if surface_type_filter and surface_type_filter != SurfaceGeometryType.HORIZONTAL_GROUND.value:
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
                error_reason=f"No surface matching filter '{surface_type_filter}' found in base ground",
            )

        px, py, pz = point_world
        signed_dist = pz - self.ground_z
        abs_d = abs(signed_dist)
        if abs_d > max_distance:
            return SurfaceQueryResult(
                surface_id="none",
                surface_type="none",
                contact_point_world=(0.0, 0.0, 0.0),
                surface_normal_world=(0.0, 0.0, 1.0),
                signed_distance=abs_d,
                friction_coeff=0.0,
                allows_regular_support=False,
                success=False,
                ray_hit_distance=None,
                error_reason=f"Point beyond max_distance={max_distance}m from ground",
            )
        return SurfaceQueryResult(
            surface_id="default_ground",
            surface_type=SurfaceGeometryType.HORIZONTAL_GROUND.value,
            contact_point_world=(px, py, self.ground_z),
            surface_normal_world=(0.0, 0.0, 1.0),
            signed_distance=signed_dist,
            friction_coeff=0.70,
            allows_regular_support=True,
            success=True,
            ray_hit_distance=None,
            error_reason=None,
        )

    def query_spatial_surface(
        self,
        point_world: Tuple[float, float, float],
        ray_direction: Optional[Tuple[float, float, float]] = None,
        max_distance: float = 10.0,
        surface_type_filter: Optional[str] = None,
    ) -> SurfaceQueryResult:
        """Baseline spatial query delegating to ground plane."""
        if ray_direction is None:
            return self.query_surface_at_point(
                point_world, max_distance=max_distance, surface_type_filter=surface_type_filter
            )

        if surface_type_filter and surface_type_filter != SurfaceGeometryType.HORIZONTAL_GROUND.value:
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
                error_reason=f"No surface matching filter '{surface_type_filter}' found in base ground",
            )

        rx, ry, rz = ray_direction
        r_len = math.sqrt(rx * rx + ry * ry + rz * rz)
        if r_len < 1e-8:
            return self.query_surface_at_point(
                point_world, max_distance=max_distance, surface_type_filter=surface_type_filter
            )

        dz = rz / r_len
        px, py, pz = point_world
        signed_dist = pz - self.ground_z

        if abs(dz) < 1e-6:
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
                error_reason=f"Ray is parallel to ground plane within {max_distance}m",
            )

        t = (self.ground_z - pz) / dz
        if 0.0 <= t <= max_distance:
            dx = rx / r_len
            dy = ry / r_len
            return SurfaceQueryResult(
                surface_id="default_ground",
                surface_type=SurfaceGeometryType.HORIZONTAL_GROUND.value,
                contact_point_world=(px + t * dx, py + t * dy, self.ground_z),
                surface_normal_world=(0.0, 0.0, 1.0),
                signed_distance=signed_dist,
                friction_coeff=0.70,
                allows_regular_support=True,
                success=True,
                ray_hit_distance=t,
                error_reason=None,
            )

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
            error_reason=f"No surface intersected along ray within {max_distance}m",
        )

    def query_ground_support_at(
        self,
        x: float,
        y: float,
        start_z: float = 50.0,
        max_fall: float = 100.0,
    ) -> SurfaceQueryResult:
        """Query primary walkable ground support at (x, y) along a vertical downward ray.

        Base implementation delegates to ground_height_at, surface_normal_at, and query_surface_at_point.
        """
        gz = self.ground_height_at(x, y)
        norm = self.surface_normal_at(x, y)
        surf_res = self.query_surface_at_point((x, y, gz))
        surf_id = surf_res.surface_id if hasattr(surf_res, "surface_id") and surf_res.surface_id not in ("none", "") else "default_ground"
        surf_type = surf_res.surface_type if hasattr(surf_res, "surface_type") and surf_res.surface_type not in ("none", "") else SurfaceGeometryType.HORIZONTAL_GROUND.value
        allows_support = getattr(surf_res, "allows_regular_support", True)
        friction = getattr(surf_res, "friction_coeff", 0.70)

        return SurfaceQueryResult(
            surface_id=surf_id,
            surface_type=surf_type,
            contact_point_world=(x, y, gz),
            surface_normal_world=norm,
            signed_distance=0.0,
            friction_coeff=friction,
            allows_regular_support=allows_support,
            success=True,
            ray_hit_distance=start_z - gz,
            error_reason=None if allows_support else f"Surface '{surf_id}' does not allow regular support",
            source_type="default",
        )

    def get_surface_by_id(self, surface_id: str) -> Optional[OrientedSurface]:
        """Lookup surface definition by ID (always None on default ground)."""
        return None

    def get_all_surfaces(self) -> List[OrientedSurface]:
        """Return registered surfaces (empty on default ground)."""
        return []


class DynamicsEnvironmentQuery(EnvironmentQuery):
    """Unified Environment Query Engine for the Procedural Dynamics Playground.

    100% backward compatible with `src.motion.framework.EnvironmentQuery`:
    - `ground_height_at(x, y) -> float`
    - `surface_normal_at(x, y) -> Tuple[float, float, float]`

    Extended with full 3D spatial query capabilities:
    - `query_surface_at_point(point_world) -> SurfaceQueryResult`
    - `query_spatial_surface(point_world, ray_direction) -> SurfaceQueryResult`
    - `get_surface_by_id(surface_id) -> Optional[OrientedSurface]`
    - `get_all_surfaces() -> List[OrientedSurface]`
    """

    def __init__(
        self,
        ground_z: float = 0.0,
        surfaces: Optional[Sequence[OrientedSurface]] = None,
        mesh_adapter: Optional[Any] = None,
        prefer_mesh: bool = False,
    ) -> None:
        super().__init__(ground_z=ground_z)
        self._surfaces: Dict[str, OrientedSurface] = {}
        self._mesh_adapter = mesh_adapter
        self._prefer_mesh = bool(prefer_mesh and mesh_adapter is not None)

        if surfaces:
            for s in surfaces:
                self.register_surface(s)

    def set_mesh_adapter(self, adapter: Any, prefer_mesh: bool = True) -> None:
        """Attach a Blender mesh environment adapter and optionally prioritize mesh over analytical."""
        self._mesh_adapter = adapter
        self._prefer_mesh = bool(prefer_mesh and adapter is not None)

    @property
    def mesh_adapter(self) -> Optional[Any]:
        """Return attached mesh environment adapter (if any)."""
        return self._mesh_adapter

    @property
    def prefer_mesh(self) -> bool:
        """Return True if mesh geometry is preferred over analytical surfaces."""
        return self._prefer_mesh

    @prefer_mesh.setter
    def prefer_mesh(self, val: bool) -> None:
        self._prefer_mesh = bool(val and self._mesh_adapter is not None)

    def has_mesh_adapter(self) -> bool:
        """Return True if an evaluated mesh adapter is attached."""
        return self._mesh_adapter is not None

    def register_surface(self, surface: OrientedSurface) -> None:
        """Register an analytical environmental surface patch."""
        self._surfaces[surface.surface_id] = surface

    def query_ground_support_at(
        self,
        x: float,
        y: float,
        start_z: float = 50.0,
        max_fall: float = 100.0,
    ) -> SurfaceQueryResult:
        """Query primary walkable ground support at (x, y) along a vertical downward ray.

        Guarantees single-hit authenticity:
        - When prefer_mesh is active: casts a downward ray against evaluated scene meshes.
          If no mesh is intersected, returns success=False with 'NO_HIT: ...' (NEVER fakes Z=0).
          If a mesh is intersected but allows_regular_support is False (steep slope, wall, ceiling),
          returns success=False with 'NON_SUPPORT_SURFACE: ...'.
        - When analytical mode is active: casts downward ray against registered analytical surfaces;
          if hit and allows_regular_support, returns it. If no analytical surface hit, falls back
          to horizontal ground at ground_z.
        """
        if self._prefer_mesh and self._mesh_adapter is not None:
            res = self._mesh_adapter.ray_cast(
                origin=(x, y, start_z),
                direction=(0.0, 0.0, -1.0),
                distance=max_fall,
            )
            if not res.success:
                return SurfaceQueryResult(
                    surface_id="none",
                    surface_type="none",
                    contact_point_world=(x, y, 0.0),
                    surface_normal_world=(0.0, 0.0, 1.0),
                    signed_distance=float("inf"),
                    friction_coeff=0.0,
                    allows_regular_support=False,
                    success=False,
                    ray_hit_distance=float("inf"),
                    error_reason=f"NO_HIT: No mesh support surface intersected at ({x:.3f}, {y:.3f}) along downward ray",
                    source_type="mesh",
                )
            if not res.allows_regular_support:
                return SurfaceQueryResult(
                    surface_id=res.surface_id,
                    surface_type=res.surface_type,
                    contact_point_world=res.contact_point_world,
                    surface_normal_world=res.surface_normal_world,
                    signed_distance=res.signed_distance,
                    friction_coeff=res.friction_coeff,
                    allows_regular_support=False,
                    success=False,
                    ray_hit_distance=res.ray_hit_distance,
                    error_reason=f"NON_SUPPORT_SURFACE: Mesh surface '{res.surface_id}' at ({x:.3f}, {y:.3f}) does not allow regular support",
                    source_type="mesh",
                )
            return res

        # Analytical mode: find highest walkable analytical surface at (x, y)
        best_z: Optional[float] = None
        best_surface: Optional[OrientedSurface] = None
        for s in self._surfaces.values():
            if not s.allows_regular_support:
                continue
            z = s.elevation_at_xy(x, y)
            if z is not None and (best_z is None or z > best_z):
                best_z = z
                best_surface = s

        if best_surface is not None and best_z is not None:
            return SurfaceQueryResult(
                surface_id=best_surface.surface_id,
                surface_type=best_surface.surface_type.value,
                contact_point_world=(x, y, best_z),
                surface_normal_world=best_surface.normal,
                signed_distance=0.0,
                friction_coeff=best_surface.friction_coeff,
                allows_regular_support=True,
                success=True,
                ray_hit_distance=start_z - best_z,
                error_reason=None,
                source_type="analytical",
            )

        # Base fallback to analytical default ground
        return SurfaceQueryResult(
            surface_id="default_ground",
            surface_type=SurfaceGeometryType.HORIZONTAL_GROUND.value,
            contact_point_world=(x, y, self.ground_z),
            surface_normal_world=(0.0, 0.0, 1.0),
            signed_distance=0.0,
            friction_coeff=0.70,
            allows_regular_support=True,
            success=True,
            ray_hit_distance=start_z - self.ground_z,
            error_reason=None,
            source_type="analytical",
        )

    def get_surface_by_id(self, surface_id: str) -> Optional[OrientedSurface]:
        """Lookup surface definition by its unique identifier."""
        return self._surfaces.get(surface_id)

    def get_all_surfaces(self) -> List[OrientedSurface]:
        """Return list of all registered environmental surfaces."""
        return list(self._surfaces.values())

    # -------------------------------------------------------------------------
    # Backward-Compatible 2.5D Height-Field Queries
    # -------------------------------------------------------------------------

    def ground_height_at(self, x: float, y: float) -> float:
        """Return highest walkable surface Z elevation at World (x, y).

        If mesh adapter is active, queries evaluated scene mesh.
        Otherwise evaluates analytical surface patches.
        Falls back to default base ground_z (0.0m) if no elevated surface hit.
        """
        if self._prefer_mesh and self._mesh_adapter is not None:
            mesh_z = self._mesh_adapter.ground_height_at(x, y)
            if mesh_z is not None:
                return float(mesh_z)
            return self.ground_z

        best_z = self.ground_z

        for s in self._surfaces.values():
            if not s.allows_regular_support:
                continue
            z = s.elevation_at_xy(x, y)
            if z is not None and z > best_z:
                best_z = z

        return best_z

    def surface_normal_at(self, x: float, y: float) -> Tuple[float, float, float]:
        """Return unit surface normal vector in World Space at (x, y).

        Returns normal of highest walkable surface at (x, y), or (0, 0, 1) if base ground.
        """
        if self._prefer_mesh and self._mesh_adapter is not None:
            mesh_n = self._mesh_adapter.surface_normal_at(x, y)
            if mesh_n is not None:
                return mesh_n
            return (0.0, 0.0, 1.0)

        best_z = self.ground_z
        best_normal = (0.0, 0.0, 1.0)

        for s in self._surfaces.values():
            if not s.allows_regular_support:
                continue
            z = s.elevation_at_xy(x, y)
            if z is not None and z >= best_z:
                best_z = z
                best_normal = s.normal

        return best_normal

    def ray_ground_elevation(
        self,
        x: float,
        y: float,
        start_z: float = 50.0,
        max_fall: float = 100.0,
    ) -> Optional[float]:
        """Strict ground query returning exact Z if hit, or None on miss.

        Guarantees that empty gaps, cliffs, or off-mesh locations do NOT return a fake ground_z.
        """
        if self._prefer_mesh and self._mesh_adapter is not None:
            return self._mesh_adapter.ground_height_at(x, y, start_z=start_z, max_fall=max_fall)

        best_z: Optional[float] = None
        for s in self._surfaces.values():
            if not s.allows_regular_support:
                continue
            z = s.elevation_at_xy(x, y)
            if z is not None:
                if best_z is None or z > best_z:
                    best_z = z
        return best_z

    # -------------------------------------------------------------------------
    # Full 3D Spatial & Wall Queries
    # -------------------------------------------------------------------------

    def query_surface_at_point(
        self,
        point_world: Tuple[float, float, float],
        max_distance: float = 5.0,
        surface_type_filter: Optional[str] = None,
    ) -> SurfaceQueryResult:
        """Query nearest surface to a 3D point in world space.

        Handles horizontal ground, inclined ramps, elevated boxes, and vertical walls.

        Args:
            point_world: (x, y, z) 3D coordinate in world space.
            max_distance: Maximum search radius. If no surface within radius, reports failure.
            surface_type_filter: Optional filter to restrict query (e.g. 'vertical_wall').

        Returns:
            SurfaceQueryResult with contact point, normal, signed distance, and friction.
        """
        if self._prefer_mesh and self._mesh_adapter is not None:
            return self._mesh_adapter.query_surface_at_point(
                point_world=point_world,
                max_distance=max_distance,
                surface_type_filter=surface_type_filter,
            )

        px, py, pz = point_world

        best_surface_id: Optional[str] = None
        best_surface_type: Optional[str] = None
        best_proj: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        best_normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)
        min_abs_dist: float = float("inf")
        best_signed_dist: float = float("inf")
        best_friction: float = 0.0
        best_support: bool = False
        found_any: bool = False

        # Base fallback candidate: global flat ground at ground_z ONLY if filter allows horizontal_ground
        if surface_type_filter in (None, "", SurfaceGeometryType.HORIZONTAL_GROUND.value):
            default_dist = abs(pz - self.ground_z)
            min_abs_dist = default_dist
            best_surface_id = "default_ground"
            best_surface_type = SurfaceGeometryType.HORIZONTAL_GROUND.value
            best_proj = (px, py, self.ground_z)
            best_normal = (0.0, 0.0, 1.0)
            best_signed_dist = pz - self.ground_z
            best_friction = 0.70
            best_support = True
            found_any = True

        # Check registered surfaces
        for s in self._surfaces.values():
            if surface_type_filter and s.surface_type.value != surface_type_filter:
                continue

            proj, s_dist, norm = s.query_closest_point(px, py, pz)
            abs_d = abs(s_dist)

            if abs_d < min_abs_dist:
                min_abs_dist = abs_d
                best_surface_id = s.surface_id
                best_surface_type = s.surface_type.value
                best_proj = proj
                best_normal = norm
                best_signed_dist = s_dist
                best_friction = s.friction_coeff
                best_support = s.allows_regular_support
                found_any = True

        if (not found_any) or (min_abs_dist > max_distance):
            filter_msg = f" matching filter '{surface_type_filter}'" if surface_type_filter else ""
            if not found_any:
                reason = f"No surface{filter_msg} registered in environment"
            else:
                reason = f"No surface{filter_msg} found within max_distance={max_distance}m (closest: {min_abs_dist:.3f}m)"

            return SurfaceQueryResult(
                surface_id="none",
                surface_type="none",
                contact_point_world=(0.0, 0.0, 0.0),
                surface_normal_world=(0.0, 0.0, 1.0),
                signed_distance=min_abs_dist if math.isfinite(min_abs_dist) else float("inf"),
                friction_coeff=0.0,
                allows_regular_support=False,
                success=False,
                ray_hit_distance=None,
                error_reason=reason,
            )

        return SurfaceQueryResult(
            surface_id=best_surface_id,
            surface_type=best_surface_type,
            contact_point_world=best_proj,
            surface_normal_world=best_normal,
            signed_distance=best_signed_dist,
            friction_coeff=best_friction,
            allows_regular_support=best_support,
            success=True,
            ray_hit_distance=None,
            error_reason=None,
        )

    def query_spatial_surface(
        self,
        point_world: Tuple[float, float, float],
        ray_direction: Optional[Tuple[float, float, float]] = None,
        max_distance: float = 10.0,
        surface_type_filter: Optional[str] = None,
    ) -> SurfaceQueryResult:
        """Query spatial surface along a specific direction or find nearest obstacle.

        Specifically designed for wall touch, vaulting, and multi-surface contacts.

        Args:
            point_world: (x, y, z) 3D coordinate in world space.
            ray_direction: Optional (dx, dy, dz) vector. If None, queries nearest non-ground obstacle
                or nearest surface matching filter.
            max_distance: Maximum search or ray propagation distance.
            surface_type_filter: Optional filter to restrict query (e.g. 'vertical_wall').

        Returns:
            SurfaceQueryResult where:
            - `signed_distance` is strictly the query point's signed distance relative to the
              surface outward normal (>0: gap/front, 0.0: on surface, <0: penetration/behind).
            - `ray_hit_distance` is the non-negative Euclidean distance traveled along the ray
              to hit the surface (None if not a directional ray query).
        """
        if self._prefer_mesh and self._mesh_adapter is not None:
            return self._mesh_adapter.query_spatial_surface(
                point_world=point_world,
                ray_direction=ray_direction,
                max_distance=max_distance,
                surface_type_filter=surface_type_filter,
            )

        if ray_direction is None:
            # Point query: nearest surface (excluding default horizontal ground if no filter given)
            px, py, pz = point_world
            best_res: Optional[SurfaceQueryResult] = None
            min_dist = float("inf")

            for s in self._surfaces.values():
                if surface_type_filter:
                    if s.surface_type.value != surface_type_filter:
                        continue
                else:
                    if s.surface_type == SurfaceGeometryType.HORIZONTAL_GROUND:
                        continue

                proj, s_dist, norm = s.query_closest_point(px, py, pz)
                abs_d = abs(s_dist)
                if abs_d < min_dist and abs_d <= max_distance:
                    min_dist = abs_d
                    best_res = SurfaceQueryResult(
                        surface_id=s.surface_id,
                        surface_type=s.surface_type.value,
                        contact_point_world=proj,
                        surface_normal_world=norm,
                        signed_distance=s_dist,
                        friction_coeff=s.friction_coeff,
                        allows_regular_support=s.allows_regular_support,
                        success=True,
                        ray_hit_distance=None,
                        error_reason=None,
                    )

            if best_res is not None:
                return best_res

            # Fallback to general query
            return self.query_surface_at_point(
                point_world, max_distance=max_distance, surface_type_filter=surface_type_filter
            )

        # Directional ray query
        rx, ry, rz = ray_direction
        r_len = math.sqrt(rx * rx + ry * ry + rz * rz)
        if r_len < 1e-8:
            return self.query_surface_at_point(
                point_world, max_distance=max_distance, surface_type_filter=surface_type_filter
            )
        dir_unit = (rx / r_len, ry / r_len, rz / r_len)

        px, py, pz = point_world
        dx, dy, dz = dir_unit

        best_t = float("inf")
        best_surface: Optional[OrientedSurface] = None
        best_proj = (0.0, 0.0, 0.0)
        best_signed_dist = float("inf")

        for s in self._surfaces.values():
            if surface_type_filter and s.surface_type.value != surface_type_filter:
                continue

            cx, cy, cz = s.center
            nx, ny, nz = s.normal

            denom = dx * nx + dy * ny + dz * nz
            # Check ray is not parallel to the surface plane
            if abs(denom) < 1e-6:
                continue

            # Plane intersection t: nx*(px + t*dx - cx) + ny*(py + t*dy - cy) + nz*(pz + t*dz - cz) = 0
            t = -((px - cx) * nx + (py - cy) * ny + (pz - cz) * nz) / denom
            if 0.0 <= t <= max_distance and t < best_t:
                # Check if intersection point falls on patch
                ix = px + t * dx
                iy = py + t * dy
                iz = pz + t * dz
                proj, s_dist, _ = s.query_closest_point(ix, iy, iz)
                if abs(s_dist) < 1e-3:
                    best_t = t
                    best_surface = s
                    best_proj = (ix, iy, iz)
                    # Normal signed distance of query point relative to surface outward normal
                    best_signed_dist = (px - cx) * nx + (py - cy) * ny + (pz - cz) * nz

        if best_surface is not None:
            return SurfaceQueryResult(
                surface_id=best_surface.surface_id,
                surface_type=best_surface.surface_type.value,
                contact_point_world=best_proj,
                surface_normal_world=best_surface.normal,
                signed_distance=best_signed_dist,
                friction_coeff=best_surface.friction_coeff,
                allows_regular_support=best_surface.allows_regular_support,
                success=True,
                ray_hit_distance=best_t,
                error_reason=None,
            )

        filter_msg = f" matching filter '{surface_type_filter}'" if surface_type_filter else ""
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
            error_reason=f"No surface{filter_msg} intersected along ray within {max_distance}m",
        )


# =============================================================================
# 4. Standard Dynamics Playground Geometry Factory
# =============================================================================

def create_standard_dynamics_playground_query() -> DynamicsEnvironmentQuery:
    """Instantiate standard 6-zone Dynamics Playground analytical surface geometry.

    Zones:
    1. Flat Ground: X in [-10, 10], Y in [-10, 5], Z = 0.0m
    2. Stairs: 5 steps at Y in [6.0, 7.5], tread=0.3m, riser=0.15m, top platform at Y in [7.5, 10.0]
    3. Sloped Ramps: +15 deg ramp up Y in [11.0, 16.0], flat bridge Y in [16.0, 18.0], -20 deg ramp down Y in [18.0, 21.68]
    4. Vertical Wall: obstacle at Y = 24.0, X in [-3, 3], Z in [0, 2.5], normal = (0, -1, 0)
    5. Vault Platform: height 0.9m, Y in [26.0, 29.0], X in [-2.5, 2.5]; Ledge Bar at Y=32.0, Z=2.2m
    6. Telemetry Debug Hub: reference platform at X in [5, 9], Y in [-5, -1], Z = 0.05m
    """
    surfaces: List[OrientedSurface] = []

    # -------------------------------------------------------------------------
    # Zone 1: Flat Ground Reference Plane
    # -------------------------------------------------------------------------
    surfaces.append(
        OrientedSurface(
            surface_id="flat_ground",
            surface_type=SurfaceGeometryType.HORIZONTAL_GROUND,
            center=(0.0, -2.5, 0.0),
            normal=(0.0, 0.0, 1.0),
            u_axis=(1.0, 0.0, 0.0),
            v_axis=(0.0, 1.0, 0.0),
            half_extents=(10.0, 7.5),
            friction_coeff=0.70,
            allows_regular_support=True,
            description="Zone 1: Flat locomotion baseline ground (Y in [-10, 5], Z=0)",
        )
    )

    # -------------------------------------------------------------------------
    # Zone 2: Alternating Standard Stairs (5 Steps + Top Landing Platform)
    # -------------------------------------------------------------------------
    step_width = 6.0       # X in [-3.0, 3.0]
    tread_depth = 0.30     # 0.3m step depth
    riser_height = 0.15    # 0.15m step height
    stair_start_y = 6.0

    for i in range(5):
        step_idx = i + 1
        tread_center_y = stair_start_y + (i * tread_depth) + (tread_depth / 2.0)
        tread_z = (i + 1) * riser_height

        # Tread surface (horizontal)
        surfaces.append(
            OrientedSurface(
                surface_id=f"stair_tread_{step_idx:02d}",
                surface_type=SurfaceGeometryType.STAIR_TREAD,
                center=(0.0, tread_center_y, tread_z),
                normal=(0.0, 0.0, 1.0),
                u_axis=(1.0, 0.0, 0.0),
                v_axis=(0.0, 1.0, 0.0),
                half_extents=(step_width / 2.0, tread_depth / 2.0),
                friction_coeff=0.65,
                allows_regular_support=True,
                description=f"Zone 2: Step {step_idx} horizontal tread at Z={tread_z:.3f}m",
            )
        )

        # Riser face (vertical, facing -Y)
        riser_y = stair_start_y + (i * tread_depth)
        riser_center_z = tread_z - (riser_height / 2.0)
        surfaces.append(
            OrientedSurface(
                surface_id=f"stair_riser_{step_idx:02d}",
                surface_type=SurfaceGeometryType.STAIR_RISER,
                center=(0.0, riser_y, riser_center_z),
                normal=(0.0, -1.0, 0.0),
                u_axis=(1.0, 0.0, 0.0),
                v_axis=(0.0, 0.0, 1.0),
                half_extents=(step_width / 2.0, riser_height / 2.0),
                friction_coeff=0.50,
                allows_regular_support=False,
                description=f"Zone 2: Step {step_idx} vertical riser facing -Y",
            )
        )

    # Stairs Landing Platform (Y in [7.5, 10.0], Z = 0.75m)
    stair_plat_start_y = stair_start_y + 5 * tread_depth  # 7.5m
    stair_plat_length = 2.5
    surfaces.append(
        OrientedSurface(
            surface_id="stair_top_platform",
            surface_type=SurfaceGeometryType.BOX_TOP,
            center=(0.0, stair_plat_start_y + stair_plat_length / 2.0, 5 * riser_height),
            normal=(0.0, 0.0, 1.0),
            u_axis=(1.0, 0.0, 0.0),
            v_axis=(0.0, 1.0, 0.0),
            half_extents=(step_width / 2.0, stair_plat_length / 2.0),
            friction_coeff=0.65,
            allows_regular_support=True,
            description="Zone 2: Stairs top transition platform at Z=0.75m",
        )
    )

    # -------------------------------------------------------------------------
    # Zone 3: Continuous Sloped Ramps (Up 15 deg, Platform, Down 20 deg)
    # -------------------------------------------------------------------------
    ramp_width = 6.0
    ramp_up_start_y = 11.0
    ramp_up_length_y = 5.0
    ramp_angle_up_rad = math.radians(15.0)

    delta_z_up = ramp_up_length_y * math.tan(ramp_angle_up_rad)  # 5.0 * tan(15 deg) = 1.3397m
    ramp_hypot_up = math.hypot(ramp_up_length_y, delta_z_up)

    norm_up_y = -math.sin(ramp_angle_up_rad)
    norm_up_z = math.cos(ramp_angle_up_rad)
    tan_up_y = math.cos(ramp_angle_up_rad)
    tan_up_z = math.sin(ramp_angle_up_rad)

    surfaces.append(
        OrientedSurface(
            surface_id="ramp_up",
            surface_type=SurfaceGeometryType.SLOPED_RAMP,
            center=(0.0, ramp_up_start_y + ramp_up_length_y / 2.0, delta_z_up / 2.0),
            normal=(0.0, norm_up_y, norm_up_z),
            u_axis=(1.0, 0.0, 0.0),
            v_axis=(0.0, tan_up_y, tan_up_z),
            half_extents=(ramp_width / 2.0, ramp_hypot_up / 2.0),
            friction_coeff=0.65,
            allows_regular_support=True,
            description=f"Zone 3: 15-degree uphill ramp (elevation 0 -> {delta_z_up:.3f}m)",
        )
    )

    # Ramp Flat Bridge (Y in [16.0, 18.0], Z = delta_z_up)
    bridge_start_y = ramp_up_start_y + ramp_up_length_y  # 16.0m
    bridge_len_y = 2.0
    surfaces.append(
        OrientedSurface(
            surface_id="ramp_top_platform",
            surface_type=SurfaceGeometryType.BOX_TOP,
            center=(0.0, bridge_start_y + bridge_len_y / 2.0, delta_z_up),
            normal=(0.0, 0.0, 1.0),
            u_axis=(1.0, 0.0, 0.0),
            v_axis=(0.0, 1.0, 0.0),
            half_extents=(ramp_width / 2.0, bridge_len_y / 2.0),
            friction_coeff=0.65,
            allows_regular_support=True,
            description=f"Zone 3: Elevated bridge connecting ramps at Z={delta_z_up:.3f}m",
        )
    )

    # Ramp Down (-20 deg, drops from delta_z_up back to 0.0)
    ramp_down_start_y = bridge_start_y + bridge_len_y  # 18.0m
    ramp_angle_down_rad = math.radians(20.0)
    ramp_down_length_y = delta_z_up / math.tan(ramp_angle_down_rad)  # ~3.681m
    ramp_hypot_down = math.hypot(ramp_down_length_y, delta_z_up)

    norm_down_y = math.sin(ramp_angle_down_rad)
    norm_down_z = math.cos(ramp_angle_down_rad)
    tan_down_y = math.cos(ramp_angle_down_rad)
    tan_down_z = -math.sin(ramp_angle_down_rad)

    surfaces.append(
        OrientedSurface(
            surface_id="ramp_down",
            surface_type=SurfaceGeometryType.SLOPED_RAMP,
            center=(0.0, ramp_down_start_y + ramp_down_length_y / 2.0, delta_z_up / 2.0),
            normal=(0.0, norm_down_y, norm_down_z),
            u_axis=(1.0, 0.0, 0.0),
            v_axis=(0.0, tan_down_y, tan_down_z),
            half_extents=(ramp_width / 2.0, ramp_hypot_down / 2.0),
            friction_coeff=0.65,
            allows_regular_support=True,
            description=f"Zone 3: 20-degree downhill ramp (elevation {delta_z_up:.3f}m -> 0)",
        )
    )

    # -------------------------------------------------------------------------
    # Zone 4: Vertical Wall (Wall Plant & Hand Push, Y = 24.0m)
    # -------------------------------------------------------------------------
    wall_y = 24.0
    wall_width = 6.0
    wall_height = 2.5
    wall_thickness = 0.40

    # Front face (facing -Y)
    surfaces.append(
        OrientedSurface(
            surface_id="vertical_wall_front",
            surface_type=SurfaceGeometryType.VERTICAL_WALL,
            center=(0.0, wall_y - wall_thickness / 2.0, wall_height / 2.0),
            normal=(0.0, -1.0, 0.0),
            u_axis=(1.0, 0.0, 0.0),
            v_axis=(0.0, 0.0, 1.0),
            half_extents=(wall_width / 2.0, wall_height / 2.0),
            friction_coeff=0.60,
            allows_regular_support=False,
            description="Zone 4: Vertical obstacle wall front surface (Z in [0, 2.5]m)",
        )
    )

    # Wall Top face (horizontal ledge, Z = 2.5m)
    surfaces.append(
        OrientedSurface(
            surface_id="vertical_wall_top",
            surface_type=SurfaceGeometryType.BOX_TOP,
            center=(0.0, wall_y, wall_height),
            normal=(0.0, 0.0, 1.0),
            u_axis=(1.0, 0.0, 0.0),
            v_axis=(0.0, 1.0, 0.0),
            half_extents=(wall_width / 2.0, wall_thickness / 2.0),
            friction_coeff=0.60,
            allows_regular_support=True,
            description="Zone 4: Wall narrow top ledge at Z=2.5m",
        )
    )

    # -------------------------------------------------------------------------
    # Zone 5: Vault Platform & Overhead Ledge Bar
    # -------------------------------------------------------------------------
    box_start_y = 26.5
    box_len_y = 3.0
    box_width = 5.0
    box_height = 0.90

    # Vault platform top
    surfaces.append(
        OrientedSurface(
            surface_id="vault_box_top",
            surface_type=SurfaceGeometryType.BOX_TOP,
            center=(0.0, box_start_y + box_len_y / 2.0, box_height),
            normal=(0.0, 0.0, 1.0),
            u_axis=(1.0, 0.0, 0.0),
            v_axis=(0.0, 1.0, 0.0),
            half_extents=(box_width / 2.0, box_len_y / 2.0),
            friction_coeff=0.65,
            allows_regular_support=True,
            description="Zone 5: 0.90m vaulting box top platform",
        )
    )

    # Vault platform front face
    surfaces.append(
        OrientedSurface(
            surface_id="vault_box_front",
            surface_type=SurfaceGeometryType.BOX_SIDE,
            center=(0.0, box_start_y, box_height / 2.0),
            normal=(0.0, -1.0, 0.0),
            u_axis=(1.0, 0.0, 0.0),
            v_axis=(0.0, 0.0, 1.0),
            half_extents=(box_width / 2.0, box_height / 2.0),
            friction_coeff=0.55,
            allows_regular_support=False,
            description="Zone 5: Vaulting box front vertical impact face",
        )
    )

    # Ledge Bar (horizontal bar for suspension / pull-up, Y = 32.0m, Z = 2.20m)
    bar_y = 32.0
    bar_z = 2.20
    bar_len_x = 4.0
    surfaces.append(
        OrientedSurface(
            surface_id="ledge_bar",
            surface_type=SurfaceGeometryType.LEDGE_BAR,
            center=(0.0, bar_y, bar_z),
            normal=(0.0, 0.0, 1.0),
            u_axis=(1.0, 0.0, 0.0),
            v_axis=(0.0, 1.0, 0.0),
            half_extents=(bar_len_x / 2.0, 0.10),
            friction_coeff=0.80,
            allows_regular_support=False,
            description="Zone 5: Overhead suspension bar at Z=2.20m",
        )
    )

    # -------------------------------------------------------------------------
    # Zone 6: Telemetry Debug Hub Reference Slab
    # -------------------------------------------------------------------------
    surfaces.append(
        OrientedSurface(
            surface_id="telemetry_debug_platform",
            surface_type=SurfaceGeometryType.HORIZONTAL_GROUND,
            center=(7.0, -3.0, 0.05),
            normal=(0.0, 0.0, 1.0),
            u_axis=(1.0, 0.0, 0.0),
            v_axis=(0.0, 1.0, 0.0),
            half_extents=(2.0, 2.0),
            friction_coeff=0.70,
            allows_regular_support=True,
            description="Zone 6: Telemetry hub visual inspection slab (X in [5, 9], Y in [-5, -1])",
        )
    )

    return DynamicsEnvironmentQuery(ground_z=0.0, surfaces=surfaces)
