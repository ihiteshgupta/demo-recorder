"""ffmpeg: 2-pass palette-optimized GIF generation."""

import asyncio
from pathlib import Path


async def generate_gif(
    video_path: Path,
    output_path: Path,
    fps: int = 10,
    width: int = 800,
    max_duration: float | None = None,
) -> Path:
    """Generate an optimized GIF from video using 2-pass palette method.

    Pass 1: Generate optimal palette from the video
    Pass 2: Apply palette for high-quality GIF

    Args:
        video_path: Input MP4 video.
        output_path: Output GIF path.
        fps: Frames per second (lower = smaller file).
        width: Output width in pixels (height auto-calculated).
        max_duration: Optional max duration in seconds.
    """
    palette_path = output_path.parent / "palette.png"

    duration_args = []
    if max_duration:
        duration_args = ["-t", str(max_duration)]

    # Pass 1: Generate palette
    filter_v = f"fps={fps},scale={width}:-1:flags=lanczos,palettegen"
    cmd_palette = [
        "ffmpeg", "-y",
        *duration_args,
        "-i", str(video_path),
        "-vf", filter_v,
        str(palette_path),
    ]
    await _run(cmd_palette)

    # Pass 2: Generate GIF using palette
    filter_complex = (
        f"fps={fps},scale={width}:-1:flags=lanczos[x];"
        f"[x][1:v]paletteuse"
    )
    cmd_gif = [
        "ffmpeg", "-y",
        *duration_args,
        "-i", str(video_path),
        "-i", str(palette_path),
        "-lavfi", filter_complex,
        str(output_path),
    ]
    await _run(cmd_gif)

    # Cleanup palette
    if palette_path.exists():
        palette_path.unlink()

    return output_path


async def _run(cmd: list[str]) -> None:
    """Run a subprocess command asynchronously using exec-style (no shell)."""
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Command failed (exit {process.returncode}):\n{error_msg}")
