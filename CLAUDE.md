# Demo Recorder

Automated voice-over demo video tool. Creates narrated screen recordings from JSON scripts using Edge TTS, Playwright, and ffmpeg.

## Quick Reference

| Task | Command |
|------|---------|
| Record a demo | `demo-recorder record script.json --output ./output/` |
| List voices | `demo-recorder voices --language en` |
| Check dependencies | `demo-recorder preflight` |
| Create template | `demo-recorder init my_demo.json` |
| Skip GIF | `demo-recorder record script.json --skip-gif` |
| Verbose mode | `demo-recorder -v record script.json` |

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -e .
playwright install chromium
```

System dependency: `ffmpeg` (install via `brew install ffmpeg`)

## Architecture

### Five-Phase Pipeline

```
Phase 1: Generate TTS audio per step (Edge TTS) → measure durations
Phase 2: Record browser with timed pauses matching narration (Playwright)
Phase 3: Merge video + audio + subtitles (ffmpeg)
Phase 4: Generate GIF preview (ffmpeg 2-pass palette)
Phase 5: Cleanup temp files
```

### Audio/Video Sync

Uses **wall-clock time** (`time.monotonic()`) to track the actual video timeline during recording. Narration audio and subtitles are placed at measured timestamps, not calculated offsets. This ensures sync even when actions take variable time (page loads, typing delays, navigation).

```
Video:  |--action--|--settle--|--narration pause--|--wait_after--|
Audio:                        |----narration----|
Subs:                         |----subtitle-----|
                              ^ pause_start_ms (wall-clock)
```

### Project Structure

```
demo-recorder/
├── pyproject.toml
├── requirements.txt
├── sample_scripts/          # JSON demo scripts
│   ├── minimal_demo.json
│   ├── visual_demo.json
│   ├── bm_platform_demo.json
│   └── ivr_workflow_demo.json
├── output/                  # Generated MP4, SRT, GIF files
└── src/demo_recorder/
    ├── cli.py               # Click CLI: record, voices, preflight, init
    ├── models.py            # Pydantic v2: DemoScript, Step, ActionType
    ├── script_loader.py     # JSON validation with Pydantic
    ├── recorder.py          # Orchestrator: 5-phase pipeline
    ├── narration.py         # Edge TTS audio + SubMaker SRT generation
    ├── browser.py           # Playwright automation + video recording
    ├── assembler.py         # ffmpeg: merge video + audio + subtitles
    ├── gif_generator.py     # ffmpeg: 2-pass palette GIF
    ├── preflight.py         # System dependency checker
    └── utils.py             # Temp dir, logging helpers
```

## JSON Script Schema

```json
{
  "metadata": {
    "title": "Demo Title",
    "description": "What this demo shows",
    "base_url": "http://localhost:8080",
    "viewport": { "width": 1920, "height": 1080 },
    "voice": "en-US-GuyNeural",
    "rate": "-5%",
    "output_name": "my_demo"
  },
  "steps": [
    {
      "id": "step_01",
      "action": "navigate",
      "url": "/page",
      "narration": "Narration text for this step.",
      "wait_after": 2000
    }
  ]
}
```

### Action Types

| Action | Required Fields | Description |
|--------|----------------|-------------|
| `navigate` | `url` | Go to URL (relative to base_url) |
| `click` | `selector` | Click element. Waits for load state after click. |
| `type` | `selector`, `value` | Type text. Optional `type_delay` (ms per char). Waits for selector visibility. |
| `scroll` | `direction`+`amount` or `selector` | Scroll page or element into view |
| `hover` | `selector` | Hover over element |
| `select` | `selector`, `value` | Select dropdown option |
| `wait` | `duration` | Explicit wait (ms) |
| `screenshot` | — | No-op marker (video is recording) |

### Narration

- Set `narration` to a text string for TTS voice-over at that step
- Set `narration` to `""` for a silent step (no audio, no subtitle)
- Voice and rate are configured in metadata, applied to all steps

## Dependencies

| Package | Purpose |
|---------|---------|
| `edge-tts>=6.1.0` | Microsoft neural TTS (free, no API key) |
| `playwright>=1.40.0` | Browser automation + video recording |
| `click>=8.1.0` | CLI framework |
| `pydantic>=2.0.0` | JSON schema validation |
| `rich>=13.0.0` | Pretty CLI output |
| **ffmpeg** (system) | Audio/video assembly, GIF generation |

## Key Implementation Details

### browser.py

- Launches headless Chromium with `record_video_dir` for automatic video capture
- `execute_action()` handles all action types with appropriate waits:
  - Click: follows up with `wait_for_load_state("load")` for navigation-triggering clicks
  - Type: calls `wait_for_selector(visible)` before filling to handle async page rendering
  - Navigate: uses `wait_until="load"` (not `networkidle` — pages with SSE/live data never reach idle)
- Each step loop iteration calls `wait_for_load_state("load")` to settle pending navigations

### narration.py

- `edge_tts.Communicate` for audio generation
- `edge_tts.SubMaker` for word-level timestamp extraction
- Returns `NarrationResult(audio_path, duration_ms, srt_text)` per step

### assembler.py

- Uses ffmpeg `adelay` filter to position each audio clip at its `pause_start_ms`
- `amix` to combine all delayed audio streams
- Burns subtitles with libass `subtitles` filter (falls back to soft subs if libass unavailable)
- Encodes as H.264 + AAC

### gif_generator.py

- Pass 1: Generate palette (`palettegen`)
- Pass 2: Apply palette (`paletteuse` with lanczos scaling)
- Output: 10 FPS, 800px wide

## Selector Tips for Scripts

- Use browser DevTools or Playwright MCP to inspect actual element IDs
- Some pages have different IDs in different modes (e.g., workflow Visual Editor uses `#name-visual` instead of `#name`)
- `button:has-text('...')` works well for buttons but can be ambiguous if text appears in multiple buttons
- For NextAuth login: field IDs are typically `#username` and `#password`
- After login clicks, allow sufficient `wait_after` (5000ms+) for session establishment

## Output Formats

| Format | Description | Typical Size |
|--------|-------------|-------------|
| MP4 | H.264 video + AAC audio + burned subtitles | 15-25 MB |
| SRT | Timed subtitle file | 5-10 KB |
| GIF | 2-pass palette optimized preview | 3-5 MB |
