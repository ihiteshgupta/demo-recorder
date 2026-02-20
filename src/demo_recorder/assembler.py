"""ffmpeg: merge video + audio + subtitles into final MP4."""

import asyncio
import subprocess
from pathlib import Path

from .narration import NarrationResult, _format_srt_time


async def build_combined_audio(
    narrations: list[NarrationResult],
    timings: list[dict],
    output_path: Path,
) -> Path:
    """Build a single audio track with narration placed at correct timestamps.

    Creates silence gaps between narrations to match video timing.
    Uses ffmpeg's adelay filter to position each audio clip.
    """
    if not any(n.duration_ms > 0 for n in narrations):
        # No narration at all — create silent audio
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", "1",
            "-c:a", "aac",
            str(output_path),
        ]
        await _run_ffmpeg(cmd)
        return output_path

    # Build filter complex: delay each audio to its pause_start_ms
    inputs = []
    filter_parts = []
    active_idx = 0

    for i, narration in enumerate(narrations):
        if narration.duration_ms <= 0 or not narration.audio_path.stat().st_size:
            continue

        timing = timings[i]
        delay_ms = timing["pause_start_ms"]

        inputs.extend(["-i", str(narration.audio_path)])
        filter_parts.append(
            f"[{active_idx}]adelay={delay_ms}|{delay_ms}[a{active_idx}]"
        )
        active_idx += 1

    if active_idx == 0:
        # All empty — silent
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", "1",
            "-c:a", "aac",
            str(output_path),
        ]
        await _run_ffmpeg(cmd)
        return output_path

    # Mix all delayed audio streams
    mix_inputs = "".join(f"[a{j}]" for j in range(active_idx))
    filter_parts.append(f"{mix_inputs}amix=inputs={active_idx}:normalize=0[out]")

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "aac",
        "-b:a", "128k",
        str(output_path),
    ]
    await _run_ffmpeg(cmd)
    return output_path


async def build_combined_srt(
    narrations: list[NarrationResult],
    timings: list[dict],
    steps: list[dict],
    output_path: Path,
) -> Path:
    """Build a combined SRT file with narration text at correct video timestamps."""
    srt_entries = []
    idx = 1

    for i, narration in enumerate(narrations):
        if narration.duration_ms <= 0:
            continue

        timing = timings[i]
        start_ms = timing["pause_start_ms"]
        end_ms = start_ms + narration.duration_ms

        text = steps[i].get("narration", "").strip()
        if not text:
            continue

        srt_entries.append(
            f"{idx}\n"
            f"{_format_srt_time(start_ms)} --> {_format_srt_time(end_ms)}\n"
            f"{text}\n"
        )
        idx += 1

    output_path.write_text("\n".join(srt_entries), encoding="utf-8")
    return output_path


async def assemble_video(
    video_path: Path,
    audio_path: Path,
    srt_path: Path,
    output_path: Path,
    burn_subtitles: bool = True,
) -> Path:
    """Merge video + audio + subtitles into final MP4.

    Args:
        video_path: Raw video from Playwright (WebM).
        audio_path: Combined narration audio (AAC).
        srt_path: SRT subtitle file.
        output_path: Final MP4 output.
        burn_subtitles: If True, burn subtitles into video.

    Returns:
        Path to the output MP4.
    """
    has_subs = srt_path.exists() and srt_path.stat().st_size > 0

    if burn_subtitles and has_subs and await _has_subtitle_filter():
        # Burn subtitles into the video using libass subtitles filter.
        # Copy SRT to a simple temp filename to avoid path escaping issues.
        import shutil
        simple_srt = srt_path.parent / "subs.srt"
        shutil.copy2(srt_path, simple_srt)

        # Use the subtitles filter with the simple path
        subtitle_filter = (
            f"subtitles='{simple_srt}'"
            ":force_style='FontSize=22,PrimaryColour=&HFFFFFF&"
            ",OutlineColour=&H40000000&,Outline=2,Shadow=1"
            ",MarginV=30,Alignment=2'"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-vf", subtitle_filter,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-map", "0:v",
            "-map", "1:a",
            "-shortest",
            str(output_path),
        ]
    elif has_subs:
        # Mux subtitles as a soft subtitle stream (no libass required)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-i", str(srt_path),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-c:s", "mov_text",
            "-map", "0:v",
            "-map", "1:a",
            "-map", "2:s",
            "-shortest",
            "-metadata:s:s:0", "language=eng",
            str(output_path),
        ]
    else:
        # No subtitles — merge video + audio, or video-only if audio is silent
        has_real_audio = audio_path.exists() and audio_path.stat().st_size > 5000
        if has_real_audio:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                "-map", "0:v",
                "-map", "1:a",
                "-shortest",
                str(output_path),
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
                "-an",
                str(output_path),
            ]

    await _run_ffmpeg(cmd)
    return output_path


async def _has_subtitle_filter() -> bool:
    """Check if ffmpeg has the subtitles filter (requires libass)."""
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-filters",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        return b"subtitles" in stdout
    except Exception:
        return False


async def _run_ffmpeg(cmd: list[str]) -> None:
    """Run an ffmpeg command asynchronously.

    Note: Uses create_subprocess_exec (not shell) to avoid command injection.
    All arguments are passed as a list, never interpolated into a shell string.
    """
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg failed (exit {process.returncode}):\n{error_msg}")
