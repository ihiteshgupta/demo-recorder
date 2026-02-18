"""Stitch branded transition clips into a recorded demo video using ffmpeg."""

import json
import subprocess
import tempfile
from pathlib import Path

from rich.console import Console

console = Console()


def _run_ffmpeg(args: list[str], description: str) -> None:
    """Run an ffmpeg command, raising on failure."""
    cmd = ["ffmpeg", "-y", *args]
    console.print(f"  [dim]{description}[/dim]")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[red]ffmpeg error:[/red] {result.stderr[-500:]}")
        raise RuntimeError(f"ffmpeg failed: {description}")


def _probe_duration(path: Path) -> float:
    """Get duration of a video file in seconds."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}")
    return float(result.stdout.strip())


def _normalize_clip(input_path: Path, output_path: Path, has_audio: bool = True) -> None:
    """Re-encode a clip to uniform H.264/AAC/30fps/1280x720."""
    if has_audio:
        _run_ffmpeg(
            [
                "-i", str(input_path),
                "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
                "-r", "30",
                "-pix_fmt", "yuv420p",
                str(output_path),
            ],
            f"Normalize {input_path.name}",
        )
    else:
        # Add silent audio track to video-only clips (Remotion outputs)
        _run_ffmpeg(
            [
                "-i", str(input_path),
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
                "-r", "30",
                "-pix_fmt", "yuv420p",
                "-shortest",
                str(output_path),
            ],
            f"Normalize + add silent audio: {input_path.name}",
        )


def _split_video(source: Path, start: float, end: float | None, output: Path) -> None:
    """Extract a segment from the source video."""
    args = ["-i", str(source), "-ss", str(start)]
    if end is not None:
        args.extend(["-t", str(end - start)])
    args.extend([
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-r", "30",
        "-pix_fmt", "yuv420p",
        str(output),
    ])
    _run_ffmpeg(args, f"Split segment {start:.1f}s-{f'{end:.1f}s' if end else 'end'}")


def _has_audio_stream(path: Path) -> bool:
    """Check if a video file has an audio stream."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def stitch_clips(
    config_path: Path,
    output_dir: Path,
    base_dir: Path | None = None,
) -> Path:
    """Concatenate clips in order from a simple clips config.

    Config format:
      {
        "clips": [
          "path/to/clip1.mp4",
          { "source": "path/to/video.mp4", "start_at": 19.0, "end_at": null },
          "path/to/clip2.mp4"
        ],
        "output_name": "final_demo"
      }
    """
    with open(config_path) as f:
        config = json.load(f)

    if "clips" not in config:
        raise ValueError("Config must have 'clips' array")

    base = base_dir or config_path.parent
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print("[bold]Stitching clips in sequence[/bold]\n")

    with tempfile.TemporaryDirectory(prefix="stitch_") as tmpdir:
        tmp = Path(tmpdir)
        segments: list[Path] = []

        for i, clip_entry in enumerate(config["clips"]):
            if isinstance(clip_entry, str):
                src = (base / clip_entry).resolve()
                start_at = 0.0
                end_at = None
                label = src.stem
            else:
                src = (base / clip_entry["source"]).resolve()
                start_at = clip_entry.get("start_at", 0.0)
                end_at = clip_entry.get("end_at")
                label = clip_entry.get("label", src.stem)

            if not src.exists():
                raise FileNotFoundError(f"Clip not found: {src}")

            has_audio = _has_audio_stream(src)

            if start_at > 0 or end_at is not None:
                # Trim the source first, then normalize
                trimmed = tmp / f"trimmed_{i:02d}.mp4"
                _split_video(src, start_at, end_at, trimmed)
                norm = tmp / f"norm_{i:02d}.mp4"
                _normalize_clip(trimmed, norm, has_audio=True)
            else:
                norm = tmp / f"norm_{i:02d}.mp4"
                _normalize_clip(src, norm, has_audio=has_audio)

            dur = _probe_duration(norm)
            trim_info = ""
            if start_at > 0:
                trim_info += f", start_at={start_at:.1f}s"
            if end_at is not None:
                trim_info += f", end_at={end_at:.1f}s"
            console.print(f"  [green]+ {label}[/green] ({dur:.1f}s{trim_info})")
            segments.append(norm)

        # Concatenate
        concat_list = tmp / "concat.txt"
        with open(concat_list, "w") as f:
            for seg in segments:
                f.write(f"file '{seg}'\n")

        output_name = config.get("output_name", "stitched") + ".mp4"
        output_path = output_dir / output_name

        _run_ffmpeg(
            [
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k",
                "-r", "30",
                "-pix_fmt", "yuv420p",
                str(output_path),
            ],
            "Concatenating all clips",
        )

        final_duration = _probe_duration(output_path)
        console.print(f"\n[bold green]Done![/bold green] {output_path}")
        console.print(f"  Duration: {final_duration:.1f}s ({len(segments)} clips)")
        return output_path


def load_stitch_config(config_path: Path) -> dict:
    """Load and validate stitch configuration JSON.

    Each transition has:
      - clip: path to the transition video
      - trim_start: seconds where the source video cut begins (white screen start)
      - trim_end: seconds where the source video cut ends (content resumes)
    The source video between trim_start and trim_end is replaced by the transition clip.
    """
    with open(config_path) as f:
        config = json.load(f)

    if "transitions" not in config:
        raise ValueError("Config must have 'transitions' array")

    for i, t in enumerate(config["transitions"]):
        if "clip" not in t:
            raise ValueError(f"Transition {i} must have 'clip'")
        if "trim_start" not in t or "trim_end" not in t:
            raise ValueError(f"Transition {i} must have 'trim_start' and 'trim_end'")
        if t["trim_end"] <= t["trim_start"]:
            raise ValueError(f"Transition {i}: trim_end must be > trim_start")

    config["transitions"].sort(key=lambda t: t["trim_start"])
    return config


def stitch_video(
    source_path: Path,
    config_path: Path,
    output_dir: Path,
    base_dir: Path | None = None,
) -> Path:
    """Stitch branded transitions into a source video.

    Args:
        source_path: Path to the source demo video.
        config_path: Path to the stitch config JSON.
        output_dir: Directory for the final output.
        base_dir: Base directory for resolving relative clip paths (defaults to config parent).

    Returns:
        Path to the final stitched video.
    """
    config = load_stitch_config(config_path)
    base = base_dir or config_path.parent

    source_path = Path(source_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    source_duration = _probe_duration(source_path)
    console.print(f"[bold]Source video:[/bold] {source_path.name} ({source_duration:.1f}s)")

    transitions = config["transitions"]
    for t in transitions:
        console.print(f"[bold]Trim:[/bold] {t['trim_start']:.1f}s → {t['trim_end']:.1f}s (cut {t['trim_end'] - t['trim_start']:.1f}s)")

    with tempfile.TemporaryDirectory(prefix="stitch_") as tmpdir:
        tmp = Path(tmpdir)
        segments: list[Path] = []

        # --- Normalize intro clip ---
        if "intro" in config and config["intro"]:
            intro_src = (base / config["intro"]).resolve()
            if not intro_src.exists():
                raise FileNotFoundError(f"Intro clip not found: {intro_src}")
            intro_norm = tmp / "intro_norm.mp4"
            has_audio = _has_audio_stream(intro_src)
            _normalize_clip(intro_src, intro_norm, has_audio=has_audio)
            segments.append(intro_norm)
            console.print(f"  [green]+ Intro[/green] ({_probe_duration(intro_norm):.1f}s)")

        # --- Build segments: source chunks interleaved with transitions ---
        # Source regions are the gaps between trim ranges
        cursor = config.get("start_at", 0.0)
        if cursor > 0:
            console.print(f"[bold]Skipping first {cursor:.1f}s of source video[/bold]")
        for i, trans in enumerate(transitions):
            # Source segment: cursor → trim_start
            if trans["trim_start"] > cursor:
                seg_path = tmp / f"seg_{i:02d}.mp4"
                _split_video(source_path, cursor, trans["trim_start"], seg_path)
                segments.append(seg_path)
                console.print(f"  [green]+ Segment {i + 1}[/green] ({cursor:.1f}s → {trans['trim_start']:.1f}s)")

            # Transition clip replaces trim_start → trim_end
            trans_src = (base / trans["clip"]).resolve()
            if not trans_src.exists():
                raise FileNotFoundError(f"Transition clip not found: {trans_src}")
            trans_norm = tmp / f"trans_{i:02d}_norm.mp4"
            has_audio = _has_audio_stream(trans_src)
            _normalize_clip(trans_src, trans_norm, has_audio=has_audio)
            segments.append(trans_norm)
            console.print(f"  [green]+ Transition {i + 1}[/green] ({_probe_duration(trans_norm):.1f}s, replaces {trans['trim_start']:.1f}s-{trans['trim_end']:.1f}s)")

            cursor = trans["trim_end"]

        # Final source segment: after last trim_end → end of video
        if cursor < source_duration:
            seg_path = tmp / f"seg_final.mp4"
            _split_video(source_path, cursor, source_duration, seg_path)
            segments.append(seg_path)
            console.print(f"  [green]+ Final segment[/green] ({cursor:.1f}s → {source_duration:.1f}s)")

        # --- Normalize outro clip ---
        if "outro" in config and config["outro"]:
            outro_src = (base / config["outro"]).resolve()
            if not outro_src.exists():
                raise FileNotFoundError(f"Outro clip not found: {outro_src}")
            outro_norm = tmp / "outro_norm.mp4"
            has_audio = _has_audio_stream(outro_src)
            _normalize_clip(outro_src, outro_norm, has_audio=has_audio)
            segments.append(outro_norm)
            console.print(f"  [green]+ Outro[/green] ({_probe_duration(outro_norm):.1f}s)")

        # --- Concatenate all segments ---
        concat_list = tmp / "concat.txt"
        with open(concat_list, "w") as f:
            for seg in segments:
                f.write(f"file '{seg}'\n")

        output_name = source_path.stem + "_branded.mp4"
        output_path = output_dir / output_name

        _run_ffmpeg(
            [
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k",
                "-r", "30",
                "-pix_fmt", "yuv420p",
                str(output_path),
            ],
            "Concatenating all segments",
        )

        final_duration = _probe_duration(output_path)
        console.print(f"\n[bold green]Done![/bold green] {output_path}")
        console.print(f"  Duration: {final_duration:.1f}s ({len(segments)} segments)")

        return output_path
