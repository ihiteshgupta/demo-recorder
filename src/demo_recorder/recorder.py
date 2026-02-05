"""Orchestrator: 5-phase recording pipeline."""

import asyncio
import logging
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .assembler import assemble_video, build_combined_audio, build_combined_srt
from .browser import record_demo
from .gif_generator import generate_gif
from .models import DemoScript
from .narration import generate_all_narrations
from .utils import ensure_output_dir, format_file_size, temp_dir, timer

console = Console()
logger = logging.getLogger("demo_recorder")


async def run_pipeline(
    script: DemoScript,
    output_dir: Path,
    verbose: bool = False,
    skip_gif: bool = False,
) -> dict[str, Path]:
    """Execute the full 5-phase recording pipeline.

    Phase 1: Pre-generate all TTS audio and measure durations
    Phase 2: Record browser with timed pauses matching narration
    Phase 3: Merge video + audio + subtitles with ffmpeg
    Phase 4: Generate GIF preview
    Phase 5: Cleanup temp files

    Returns dict of output file paths.
    """
    output_dir = ensure_output_dir(output_dir)
    output_name = script.metadata.output_name
    outputs: dict[str, Path] = {}

    with temp_dir() as tmp:
        audio_dir = tmp / "audio"
        audio_dir.mkdir()
        video_dir = tmp / "video"
        video_dir.mkdir()

        steps_data = [
            {"id": s.id, "narration": s.narration}
            for s in script.steps
        ]

        # Phase 1: Generate narrations
        console.print("\n[bold cyan]Phase 1:[/bold cyan] Generating narrations...")
        with timer("Narration generation", logger):
            narrations = await generate_all_narrations(
                steps=steps_data,
                output_dir=audio_dir,
                voice=script.metadata.voice,
                rate=script.metadata.rate,
            )

        durations = [n.duration_ms for n in narrations]
        total_narration = sum(durations)
        narrated_steps = sum(1 for d in durations if d > 0)
        console.print(
            f"  {narrated_steps}/{len(script.steps)} steps with narration, "
            f"total audio: {total_narration / 1000:.1f}s"
        )

        # Phase 2: Record browser
        console.print("\n[bold cyan]Phase 2:[/bold cyan] Recording browser session...")
        with timer("Browser recording", logger):
            video_path, timings = await record_demo(
                script=script,
                narration_durations=durations,
                video_dir=video_dir,
            )

        timing_dicts = [
            {
                "step_id": t.step_id,
                "action_start_ms": t.action_start_ms,
                "pause_start_ms": t.pause_start_ms,
                "pause_end_ms": t.pause_end_ms,
            }
            for t in timings
        ]

        # Phase 3: Assemble final video
        console.print("\n[bold cyan]Phase 3:[/bold cyan] Assembling final video...")

        # 3a: Build combined audio track
        combined_audio = tmp / "combined_audio.aac"
        with timer("Audio assembly", logger):
            await build_combined_audio(narrations, timing_dicts, combined_audio)

        # 3b: Build combined SRT
        srt_output = output_dir / f"{output_name}.srt"
        await build_combined_srt(narrations, timing_dicts, steps_data, srt_output)
        outputs["srt"] = srt_output
        console.print(f"  SRT saved: {srt_output}")

        # 3c: Merge video + audio + subtitles
        mp4_output = output_dir / f"{output_name}.mp4"
        with timer("Video assembly", logger):
            await assemble_video(
                video_path=video_path,
                audio_path=combined_audio,
                srt_path=srt_output,
                output_path=mp4_output,
            )
        outputs["mp4"] = mp4_output

        mp4_size = format_file_size(mp4_output.stat().st_size)
        console.print(f"  MP4 saved: {mp4_output} ({mp4_size})")

        # Phase 4: Generate GIF
        if not skip_gif:
            console.print("\n[bold cyan]Phase 4:[/bold cyan] Generating GIF preview...")
            gif_output = output_dir / f"{output_name}.gif"
            with timer("GIF generation", logger):
                await generate_gif(
                    video_path=mp4_output,
                    output_path=gif_output,
                    max_duration=30.0,  # Cap GIF at 30s for size
                )
            outputs["gif"] = gif_output

            gif_size = format_file_size(gif_output.stat().st_size)
            console.print(f"  GIF saved: {gif_output} ({gif_size})")
        else:
            console.print("\n[bold cyan]Phase 4:[/bold cyan] GIF generation skipped.")

        # Phase 5: Cleanup (automatic via temp_dir context manager)
        console.print("\n[bold cyan]Phase 5:[/bold cyan] Cleaning up temp files...")

    console.print("\n[bold green]Recording complete![/bold green]")
    for fmt, path in outputs.items():
        console.print(f"  {fmt.upper()}: {path}")

    return outputs
