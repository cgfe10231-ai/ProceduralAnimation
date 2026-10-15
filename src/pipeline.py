"""End-to-end procedural animation pipeline orchestrator."""

import sys
from src.config import PipelineConfig
from src.scene import setup_scene
from src.camera import setup_camera
from src.lighting import setup_lighting
from src.render import configure_render, save_blend_file, render_still
from src.validation import verify_pipeline_outputs

def run_pipeline(config: PipelineConfig = None) -> dict:
    """Run the minimal end-to-end procedural pipeline."""
    if config is None:
        config = PipelineConfig()

    print("=" * 60)
    print("PROCEDURAL ANIMATION PIPELINE: EXECUTION STARTED")
    print(f"Target Resolution: {config.resolution_x}x{config.resolution_y}")
    print(f"Target Timeline: {config.fps} FPS, {config.total_frames} Frames ({config.frame_start}..{config.frame_end})")
    print(f"Render Engine: {config.render_engine}")
    print(f"Output Directory: {config.output_dir}")
    print("=" * 60)

    # 1. Setup Scene
    scene = setup_scene(config)
    print(f"[PIPELINE_STAGE] 1. Scene created: {scene.name}")

    # 2. Setup Camera
    cam = setup_camera(config, scene)
    print(f"[PIPELINE_STAGE] 2. Camera created: {cam.name}")

    # 3. Setup Lighting
    light = setup_lighting(config)
    print(f"[PIPELINE_STAGE] 3. Lighting created: {light.name}")

    # 4. Configure Render Settings
    configure_render(config, scene)
    print(f"[PIPELINE_STAGE] 4. Render configured (Engine: {config.render_engine})")

    # 5. Save .blend file
    saved_blend = save_blend_file(config)
    print(f"[PIPELINE_STAGE] 5. .blend file saved: {saved_blend}")

    # 6. Render preview still
    saved_render = render_still(config, frame=config.frame_start)
    print(f"[PIPELINE_STAGE] 6. Preview image rendered: {saved_render}")

    # 7. Validate outputs
    results = verify_pipeline_outputs(config)
    print(f"[PIPELINE_STAGE] 7. Output integrity validated successfully:")
    print(f"    - Scene FPS: {results['scene_settings']['fps']}")
    print(f"    - Frame Range: {results['scene_settings']['frame_range']}")
    print(f"    - .blend Size: {results['blend_file']['size_bytes']} bytes")
    print(f"    - Render Image Size: {results['render_image']['size_bytes']} bytes")
    print(f"    - Render Image Dimensions: {results['render_image']['dimensions']}")
    print("=" * 60)
    print("PROCEDURAL ANIMATION PIPELINE: COMPLETED SUCCESSFULLY")
    print("=" * 60)

    return results

if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception as e:
        print(f"[PIPELINE_FATAL_ERROR] {e}", file=sys.stderr)
        sys.exit(1)
