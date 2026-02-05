"""Edge TTS audio generation and SRT subtitle creation."""

import asyncio
import struct
from dataclasses import dataclass
from pathlib import Path

import edge_tts


@dataclass
class NarrationResult:
    """Result from generating narration for a single step."""
    audio_path: Path
    duration_ms: int
    srt_text: str  # SRT-formatted subtitles for this step


def _format_srt_time(ms: int) -> str:
    """Format milliseconds as SRT timestamp: HH:MM:SS,mmm"""
    hours = ms // 3_600_000
    ms %= 3_600_000
    minutes = ms // 60_000
    ms %= 60_000
    seconds = ms // 1_000
    millis = ms % 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


async def _get_audio_duration_mp3(path: Path) -> int:
    """Estimate MP3 duration in ms by reading frames.

    Falls back to file-size estimation if parsing fails.
    """
    data = path.read_bytes()

    # Try to find MPEG audio frames and sum their durations
    total_frames = 0
    i = 0
    sample_rate = 24000  # Edge TTS default

    while i < len(data) - 4:
        # Look for frame sync (11 set bits)
        if data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0:
            # Parse header
            header = struct.unpack(">I", data[i : i + 4])[0]
            version = (header >> 19) & 0x03
            layer = (header >> 17) & 0x03

            if version == 0 or layer == 0:
                i += 1
                continue

            # Get bitrate and sample rate for frame size calculation
            bitrate_idx = (header >> 12) & 0x0F
            sr_idx = (header >> 10) & 0x03
            padding = (header >> 9) & 0x01

            if bitrate_idx == 0 or bitrate_idx == 15 or sr_idx == 3:
                i += 1
                continue

            # MPEG1 Layer 3 bitrate table
            bitrate_table = [0, 32, 40, 48, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
            sr_table_v1 = [44100, 48000, 32000]

            if version == 3:  # MPEG1
                bitrate = bitrate_table[bitrate_idx] * 1000
                sr = sr_table_v1[sr_idx]
            else:
                i += 1
                continue

            if bitrate == 0 or sr == 0:
                i += 1
                continue

            sample_rate = sr
            frame_size = (144 * bitrate // sr) + padding
            if frame_size < 4:
                i += 1
                continue

            total_frames += 1
            i += frame_size
        else:
            i += 1

    if total_frames > 0:
        # Each MPEG1 Layer 3 frame = 1152 samples
        total_samples = total_frames * 1152
        return int(total_samples * 1000 / sample_rate)

    # Fallback: estimate from file size assuming ~48kbps (Edge TTS typical)
    return int(len(data) * 8 / 48)


async def generate_narration(
    text: str,
    output_path: Path,
    voice: str = "en-US-AriaNeural",
    rate: str = "+0%",
) -> NarrationResult:
    """Generate TTS audio and SRT subtitles for a single narration text.

    Returns NarrationResult with audio file path, duration, and SRT entries.
    """
    if not text.strip():
        # No narration — return empty result
        output_path.write_bytes(b"")
        return NarrationResult(audio_path=output_path, duration_ms=0, srt_text="")

    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    submaker = edge_tts.SubMaker()

    audio_chunks: list[bytes] = []
    last_offset = 0.0
    last_duration = 0.0

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            submaker.feed(chunk)
            last_offset = chunk.get("offset", last_offset)
            last_duration = chunk.get("duration", last_duration)

    audio_data = b"".join(audio_chunks)
    output_path.write_bytes(audio_data)

    # Get duration: prefer WordBoundary timestamps, fallback to MP3 parsing
    if last_offset > 0:
        # offset/duration are in 100-nanosecond ticks (Windows FILETIME units)
        # Divide by 10,000 to convert to milliseconds
        duration_ms = int((last_offset + last_duration) / 10_000)
    elif audio_data:
        duration_ms = await _get_audio_duration_mp3(output_path)
    else:
        duration_ms = 0

    # Generate SRT text from submaker
    srt_text = submaker.get_srt() if audio_data else ""

    return NarrationResult(
        audio_path=output_path,
        duration_ms=duration_ms,
        srt_text=srt_text,
    )


async def generate_all_narrations(
    steps: list[dict],
    output_dir: Path,
    voice: str = "en-US-AriaNeural",
    rate: str = "+0%",
) -> list[NarrationResult]:
    """Generate narration for all steps sequentially.

    Args:
        steps: List of step dicts with 'id' and 'narration' keys.
        output_dir: Directory to save audio files.
        voice: Edge TTS voice name.
        rate: Speech rate adjustment.

    Returns:
        List of NarrationResult for each step.
    """
    results = []
    for step in steps:
        narration_text = step.get("narration", "")
        step_id = step.get("id", f"step_{len(results)}")
        audio_path = output_dir / f"{step_id}.mp3"

        result = await generate_narration(
            text=narration_text,
            output_path=audio_path,
            voice=voice,
            rate=rate,
        )
        results.append(result)

    return results


def list_voices_sync(language: str = "en") -> list[dict]:
    """List available Edge TTS voices for a language prefix."""
    return asyncio.run(_list_voices(language))


async def _list_voices(language: str = "en") -> list[dict]:
    """List available Edge TTS voices."""
    voices = await edge_tts.list_voices()
    filtered = [
        {
            "name": v["ShortName"],
            "gender": v["Gender"],
            "locale": v["Locale"],
        }
        for v in voices
        if v["Locale"].lower().startswith(language.lower())
    ]
    return sorted(filtered, key=lambda v: (v["locale"], v["name"]))
