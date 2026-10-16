"""End-to-end procedural animation pipeline orchestrator."""

import sys
from src.config import PipelineConfig
from src.scene import setup_scene
from src.camera import setup_camera
from src.lighting import setup_lighting
from src.render import configure_render, save_blend_file, render_preview_stills
from src.validation import verify_pipeline_outputs

def run_pipeline(config: PipelineConfig = None) -> dict:
    """Run the procedural 3D scene, lighting, camera, and render pipeline."""
    if config is None:
        config = PipelineConfig()

    print("=" * 60)
    print("PROCEDURAL ANIMATION PIPELINE: TASK 3 EXECUTION STARTED")
    print(f"Target Resolution: {config.resolution_x}x{config.resolution_y}")
    print(f"Target Timeline: {config.fps} FPS, {config.total_frames} Frames ({config.frame_start}..{config.frame_end})")
    print(f"Random Seed: {config.random_seed}")
    print(f"Render Engine: {config.render_engine}")
    print(f"Output Directory: {config.output_dir}")
    print("=" * 60)

    # 1. Setup Scene (Ground, Buildings, Pillars, Corridor Guides)
    scene, layout = setup_scene(config)
    print(f"[PIPELINE_STAGE] 1. Scene created: {scene.name}")
    print(f"    - Ground: {layout.ground_size[0]}m x {layout.ground_size[1]}m, Top Z = 0.0")
    print(f"    - Environment Elements: {len(layout.buildings)} buildings, {len(layout.pillars)} pillars")
    print(f"    - Corridor Clearance: {config.corridor_clearance}m buffer respected")

    # 2. Setup Lighting (Key, Fill, World Ambient)
    lights = setup_lighting(config)
    print(f"[PIPELINE_STAGE] 2. Lighting setup complete: {lights['key_light'].name}, {lights['fill_light'].name}")

    # 3. Setup Camera (Track-To constraint, 50mm, keyframe animation)
    cam_info = setup_camera(config, scene)
    print(f"[PIPELINE_STAGE] 3. Camera setup complete: {cam_info['camera'].name} tracking {cam_info['target'].name}")

    # 4. Configure Render Settings
    configure_render(config, scene)
    print(f"[PIPELINE_STAGE] 4. Render configured (Engine: {config.render_engine})")

    # 5. Save .blend file
    saved_blend = save_blend_file(config)
    print(f"[PIPELINE_STAGE] 5. .blend file saved: {saved_blend}")

    # 6. Render preview stills across timeline
    print(f"[PIPELINE_STAGE] 6. Rendering preview stills at frames: {config.preview_frames}...")
    rendered_stills = render_preview_stills(config)
    for path in rendered_stills:
        print(f"    - Rendered: {path}")

    # 7. Validate all outputs, spatial constraints, and camera motion
    print("[PIPELINE_STAGE] 7. Running comprehensive output verification...")
    results = verify_pipeline_outputs(config, layout)
    print("[PIPELINE_STAGE] 7. Output integrity validated successfully:")
    print(f"    - Scene FPS: {results['scene_settings']['fps']}")
    print(f"    - Frame Range: {results['scene_settings']['frame_range']}")
    print(f"    - Ground Top Z: {results['ground']['top_z']}")
    print(f"    - Corridor Clearance Verified: {results['environment']['corridor_clearance_verified']}")
    print(f"    - Camera Frame 1 Pos: {results['camera']['frame_1_location']}")
    print(f"    - Camera Frame 180 Pos: {results['camera']['frame_180_location']}")
    print(f"    - Camera Displacement: {results['camera']['displacement_meters']}m")
    print(f"    - .blend Size: {results['blend_file']['size_bytes']} bytes")
    print(f"    - Preview Visual Variance: {results['preview_visual_variance_verified']}")
    print("=" * 60)
    print("PROCEDURAL ANIMATION PIPELINE: TASK 3 COMPLETED SUCCESSFULLY")
    print("=" * 60)

    return results

if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception as e:
        print(f"[PIPELINE_FATAL_ERROR] {e}", file=sys.stderr)
        sys.exit(1)
