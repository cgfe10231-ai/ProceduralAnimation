"""Unified Configuration Management for Procedural Animation Engine."""

import os
from dataclasses import dataclass, field
from typing import Tuple, List

@dataclass
class PipelineConfig:
    """Project-wide configuration parameters."""

    # Project filesystem paths
    project_root: str = field(default_factory=lambda: os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    output_dir_name: str = "output"
    
    # Timeline parameters (Phase 1 Acceptance Defaults)
    fps: int = 24
    frame_start: int = 1
    frame_end: int = 360
    
    # Resolution (1280x720 16:9 HD)
    resolution_x: int = 1280
    resolution_y: int = 720
    resolution_percentage: int = 100
    
    # Render Engine & Quality
    render_engine: str = "BLENDER_WORKBENCH"  # Fast low-cost preview
    preview_samples: int = 1
    file_format: str = "PNG"
    color_mode: str = "RGB"
    
    # Determinism
    random_seed: int = 42

    # Scene & Ground parameters (World Convention: Z=Up, ground top at Z=0.0)
    ground_size: Tuple[float, float] = (24.0, 24.0)  # (width X, length Y) in meters
    ground_thickness: float = 0.2
    ground_color: Tuple[float, float, float, float] = (0.18, 0.20, 0.22, 1.0)

    # Environment layout parameters
    building_count: int = 6
    pillar_count: int = 8
    corridor_clearance: float = 2.4  # Minimum clear distance around character walking path
    building_color: Tuple[float, float, float, float] = (0.45, 0.48, 0.52, 1.0)
    pillar_color: Tuple[float, float, float, float] = (0.75, 0.45, 0.25, 1.0)

    # Reserved character trajectory corridor waypoints:
    # 1. Start / Stand: (0.0, -8.0, 0.0)
    # 2. Walk to Stop/Turn area: (0.0, 0.0, 0.0)
    # 3. Exit direction: towards (3.5, 7.0, 0.0)
    character_path_points: List[Tuple[float, float, float]] = field(
        default_factory=lambda: [(0.0, -8.0, 0.0), (0.0, 0.0, 0.0), (3.5, 7.0, 0.0)]
    )

    # Lighting parameters
    key_light_energy: float = 2500.0
    key_light_location: Tuple[float, float, float] = (8.0, -8.0, 12.0)
    fill_light_energy: float = 800.0
    fill_light_location: Tuple[float, float, float] = (-6.0, 6.0, 8.0)

    # Camera parameters
    camera_focal_length: float = 50.0
    # Preview stills to render and validate across the timeline
    preview_frames: Tuple[int, ...] = (1, 180)

    # Output artifact file names
    blend_filename: str = "procedural_scene.blend"
    # Task 4A isolated character prototype artifacts (must not overwrite Task 3 files)
    character_blend_filename: str = "character_prototype.blend"
    character_preview_filename: str = "preview_character_placeholder.png"
    # Task 4B isolated rig prototype artifacts (must not overwrite Task 3 or Task 4A files)
    character_rig_blend_filename: str = "character_rig_prototype.blend"
    character_rig_preview_filename: str = "preview_character_rig_pose.png"
    # Task 4C isolated leg IK prototype artifacts (must not overwrite Task 3, 4A, or 4B files)
    character_ik_blend_filename: str = "character_ik_prototype.blend"
    character_ik_preview_filename: str = "preview_character_ik_pose.png"
    # Task 4D isolated foot support & ground contact artifacts
    character_foot_contact_blend_filename: str = "character_foot_contact_prototype.blend"
    character_foot_contact_preview_filename: str = "preview_character_foot_contact.png"
    # Task 5A isolated procedural walk cycle parameters & artifacts
    walk_cycle_frames: int = 48  # 2.0 seconds per full gait cycle at 24 FPS
    walk_step_length: float = 0.18  # Forward (+Y) swing reach in meters
    walk_step_height: float = 0.14  # Vertical (+Z) swing foot lift in meters
    walk_pelvis_crouch: float = -0.026  # Base pelvis vertical crouch (m) keeping stance leg within strict IK reach
    walk_pelvis_bob_amp: float = 0.010  # Vertical pelvis bobbing amplitude (m) at 2x gait frequency
    walk_pelvis_sway_amp: float = 0.018  # Lateral (+/-X) pelvis weight shift amplitude (m)
    walk_pelvis_yaw_deg: float = 5.0  # Pelvis axial twist amplitude (deg)
    walk_pelvis_roll_deg: float = 2.0  # Pelvis coronal tilt amplitude (deg)
    walk_torso_yaw_deg: float = 6.5  # Spine counter-twist amplitude (deg)
    walk_torso_lean_deg: float = 3.0  # Spine forward lean angle (deg)
    walk_arm_swing_deg: float = 26.0  # Upper-arm contra-lateral swing amplitude (deg)
    walk_elbow_base_deg: float = 18.0  # Base forearm flexion angle (deg)
    walk_elbow_swing_deg: float = 14.0  # Dynamic forearm flexion amplitude (deg)
    walk_cycle_blend_filename: str = "character_walk_cycle.blend"
    walk_cycle_preview_filename: str = "preview_character_walk_cycle.png"
    # Task 5B isolated continuous forward walking parameters & artifacts
    forward_walk_cycles: int = 3  # 3 full cycles = 144 frames (6.0s @ 24 FPS)
    forward_walk_step_length: float = 0.24  # Half-cycle step length (m); full cycle stride = 0.48m
    forward_walk_step_height: float = 0.14  # Vertical (+Z) swing foot clearance (m)
    forward_walk_pelvis_crouch: float = -0.032  # Base pelvis crouch keeping full stride strictly inside 0.82m IK reach
    forward_walk_preview_frames: Tuple[int, ...] = (1, 37, 85, 133)
    forward_walk_blend_filename: str = "character_forward_walk.blend"
    # Task 5C isolated start -> accelerate -> steady walk -> decelerate -> stop parameters & artifacts
    start_stop_stand_start_frames: int = 12  # Initial stationary standing frames (tau in [0, 12], frames 1..13)
    start_stop_accel_frames: int = 54  # Smooth acceleration phase duration (tau in [12, 66], 2 steps: 30 + 24 frames)
    start_stop_steady_frames: int = 72  # Constant-speed walking phase duration (tau in [66, 138], 3 steps of 24 frames)
    start_stop_decel_frames: int = 54  # Smooth deceleration phase duration (tau in [138, 192], 2 steps: 24 + 30 frames)
    start_stop_stand_end_frames: int = 12  # Final stationary standing frames (tau in [192, 203], frames 193..204)
    start_stop_target_speed: float = 0.24  # Target steady walking speed (m/s) == 0.010 m/frame @ 24 FPS
    start_stop_init_step_length: float = 0.15  # First initiation/deceleration step length (m)
    start_stop_steady_step_length: float = 0.24  # Steady half-cycle step length (m)
    start_stop_accel_pelvis_drop: float = -0.008  # Subtle extra pelvis lowering during start/decel transitions (m)
    start_stop_accel_torso_lean_deg: float = 1.8  # Subtle extra forward torso lean during acceleration (deg)
    start_stop_decel_torso_lean_deg: float = -1.2  # Subtle torso counter-lean / upright recovery during deceleration (deg)
    start_stop_preview_frames: Tuple[int, ...] = (1, 30, 103, 155, 204)
    start_stop_blend_filename: str = "character_start_stop_walk.blend"

    @property
    def total_frames(self) -> int:
        return self.frame_end - self.frame_start + 1

    @property
    def output_dir(self) -> str:
        path = os.path.join(self.project_root, self.output_dir_name)
        os.makedirs(path, exist_ok=True)
        return path

    @property
    def blend_file_path(self) -> str:
        return os.path.join(self.output_dir, self.blend_filename)

    def get_preview_image_path(self, frame: int) -> str:
        filename = f"preview_frame_{frame:04d}.png"
        return os.path.join(self.output_dir, filename)

    @property
    def preview_image_path(self) -> str:
        """Default to first preview frame."""
        return self.get_preview_image_path(self.preview_frames[0])

    @property
    def character_blend_path(self) -> str:
        return os.path.join(self.output_dir, self.character_blend_filename)

    @property
    def character_preview_path(self) -> str:
        return os.path.join(self.output_dir, self.character_preview_filename)

    @property
    def character_rig_blend_path(self) -> str:
        return os.path.join(self.output_dir, self.character_rig_blend_filename)

    @property
    def character_rig_preview_path(self) -> str:
        return os.path.join(self.output_dir, self.character_rig_preview_filename)

    @property
    def character_ik_blend_path(self) -> str:
        return os.path.join(self.output_dir, self.character_ik_blend_filename)

    @property
    def character_ik_preview_path(self) -> str:
        return os.path.join(self.output_dir, self.character_ik_preview_filename)

    @property
    def character_foot_contact_blend_path(self) -> str:
        return os.path.join(self.output_dir, self.character_foot_contact_blend_filename)

    @property
    def character_foot_contact_preview_path(self) -> str:
        return os.path.join(self.output_dir, self.character_foot_contact_preview_filename)

    @property
    def walk_cycle_blend_path(self) -> str:
        return os.path.join(self.output_dir, self.walk_cycle_blend_filename)

    @property
    def walk_cycle_preview_path(self) -> str:
        return os.path.join(self.output_dir, self.walk_cycle_preview_filename)

    @property
    def forward_walk_frames(self) -> int:
        return self.walk_cycle_frames * self.forward_walk_cycles

    @property
    def forward_walk_stride_length(self) -> float:
        return 2.0 * self.forward_walk_step_length

    @property
    def forward_walk_speed(self) -> float:
        cycle_seconds = self.walk_cycle_frames / float(self.fps)
        return self.forward_walk_stride_length / cycle_seconds

    @property
    def forward_walk_blend_path(self) -> str:
        return os.path.join(self.output_dir, self.forward_walk_blend_filename)

    def get_forward_walk_preview_path(self, frame: int) -> str:
        return os.path.join(self.output_dir, f"preview_forward_walk_frame_{frame:04d}.png")

    @property
    def start_stop_total_frames(self) -> int:
        return (
            self.start_stop_stand_start_frames
            + self.start_stop_accel_frames
            + self.start_stop_steady_frames
            + self.start_stop_decel_frames
            + self.start_stop_stand_end_frames
        )

    @property
    def start_stop_blend_path(self) -> str:
        return os.path.join(self.output_dir, self.start_stop_blend_filename)

    def get_start_stop_preview_path(self, frame: int) -> str:
        return os.path.join(self.output_dir, f"preview_start_stop_frame_{frame:04d}.png")
