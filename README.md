# Demo Recorder

Create narrated demo videos from JSON scripts. Define your walkthrough steps declaratively — navigate, click, type, scroll — and Demo Recorder handles the browser recording, text-to-speech narration, subtitle generation, and final video assembly automatically.

**No screen recording software. No manual voice-over. No video editing.** Just write a JSON script and get a polished MP4 with synchronized narration and subtitles.

## How It Works

```
JSON Script → 5-Phase Pipeline → MP4 + SRT + GIF
```

1. **Generate TTS audio** per step using Microsoft Edge Neural Voices (free, no API key)
2. **Record the browser** with Playwright, inserting timed pauses matching each narration clip
3. **Assemble the final video** — merge video + audio + burned subtitles with ffmpeg
4. **Generate a GIF preview** (optional, 2-pass palette optimization)
5. **Cleanup** temporary files

Audio and video stay in sync using wall-clock timestamps captured during recording, so variable page load times don't cause drift.

## Installation

### Prerequisites

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) (system install)

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

### Setup

```bash
git clone https://github.com/ihiteshgupta/demo-recorder.git
cd demo-recorder
python -m venv venv
source venv/bin/activate
pip install -e .
playwright install chromium
```

### Verify

```bash
demo-recorder preflight
```

This checks that ffmpeg, Playwright, and edge-tts are all available.

## Quick Start

### 1. Create a script

```bash
demo-recorder init my_demo.json
```

This generates a template script. Edit it to match your application:

```json
{
  "metadata": {
    "title": "My App Demo",
    "description": "Walkthrough of the main features",
    "base_url": "http://localhost:8080",
    "viewport": { "width": 1280, "height": 720 },
    "voice": "en-US-AriaNeural",
    "rate": "+0%",
    "output_name": "my_demo"
  },
  "steps": [
    {
      "id": "step_01",
      "action": "navigate",
      "url": "/",
      "narration": "Welcome to the app. Let's start from the home page.",
      "wait_after": 2000
    },
    {
      "id": "step_02",
      "action": "click",
      "selector": "button:has-text('Get Started')",
      "narration": "Click Get Started to begin.",
      "wait_after": 1000
    },
    {
      "id": "step_03",
      "action": "type",
      "selector": "#name",
      "value": "Demo User",
      "narration": "Enter your name in the field.",
      "type_delay": 50,
      "wait_after": 500
    }
  ]
}
```

### 2. Record

```bash
demo-recorder record my_demo.json --output ./output/
```

### 3. Output

```
output/
├── my_demo.mp4   # H.264 video with narration + burned subtitles
├── my_demo.srt   # Subtitle file
└── my_demo.gif   # Animated preview (10fps, 800px wide)
```

## CLI Reference

```
Usage: demo-recorder [OPTIONS] COMMAND [ARGS]...

Commands:
  record     Record a demo from a JSON script file
  voices     List available Edge TTS voices
  preflight  Check system dependencies
  init       Initialize a sample demo script template
```

### record

```bash
demo-recorder record script.json [OPTIONS]

Options:
  -o, --output PATH   Output directory (default: ./output)
  --skip-gif           Skip GIF generation
  -v, --verbose        Enable debug logging
```

### voices

```bash
demo-recorder voices --language en    # English voices
demo-recorder voices --language fr    # French voices
demo-recorder voices --language hi    # Hindi voices
```

### preflight

```bash
demo-recorder preflight
```

### init

```bash
demo-recorder init my_demo.json
```

## Script Reference

### Metadata

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | string | `"Demo Recording"` | Title for logging |
| `description` | string | `""` | Description for documentation |
| `base_url` | string | `"http://localhost:8080"` | Base URL for relative navigation |
| `viewport` | object | `{width: 1280, height: 720}` | Browser viewport size |
| `voice` | string | `"en-US-AriaNeural"` | Edge TTS voice name |
| `rate` | string | `"+0%"` | Speech rate adjustment (e.g., `"-10%"`, `"+20%"`) |
| `output_name` | string | `"demo"` | Base name for output files |

### Action Types

| Action | Required Fields | Description |
|--------|----------------|-------------|
| `navigate` | `url` | Go to URL (relative to `base_url`) |
| `click` | `selector` | Click an element. Waits for page load after click. |
| `type` | `selector`, `value` | Type text into a field. Optional `type_delay` (ms per char). |
| `scroll` | `direction` + `amount` or `selector` | Scroll page or scroll element into view |
| `hover` | `selector` | Hover over an element |
| `select` | `selector`, `value` | Select a dropdown option |
| `wait` | `duration` | Pause for a duration (ms) |
| `screenshot` | — | No-op marker (video is already recording) |

### Step Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | string | *required* | Unique step identifier |
| `action` | string | *required* | One of the action types above |
| `narration` | string | `""` | Text-to-speech narration. Empty string = silent step. |
| `wait_after` | int | `500` | Pause after action completes (ms) |
| `selector` | string | — | CSS selector for the target element |
| `url` | string | — | URL path for `navigate` |
| `value` | string | — | Text for `type` or option for `select` |
| `type_delay` | int | `50` | Delay between keystrokes (ms) |
| `direction` | string | — | `"up"` or `"down"` for `scroll` |
| `amount` | int | — | Pixels to scroll |
| `duration` | int | — | Wait duration in ms (for `wait` action) |

## Architecture

```
src/demo_recorder/
├── cli.py            # Click CLI commands
├── models.py         # Pydantic v2 schema validation
├── script_loader.py  # JSON loading + validation
├── recorder.py       # 5-phase pipeline orchestrator
├── narration.py      # Edge TTS audio + SRT generation
├── browser.py        # Playwright browser automation
├── assembler.py      # ffmpeg video + audio + subtitle merge
├── gif_generator.py  # ffmpeg 2-pass GIF generation
├── preflight.py      # Dependency checker
└── utils.py          # Temp dir, logging, helpers
```

### Audio/Video Sync

The recorder uses wall-clock time (`time.monotonic()`) to track the actual video timeline during browser recording. When a step has narration, the recorder pauses the browser for the exact narration duration. The timestamp of that pause is recorded and used later to position the audio clip and subtitle in the final video.

```
Video:  |--action--|--settle--|--narration pause--|--wait_after--|
Audio:                        |----narration----|
Subs:                         |----subtitle-----|
                              ^ pause_start_ms (wall-clock)
```

This avoids drift caused by variable page load times, animation delays, or network latency.

## Dependencies

| Package | Purpose |
|---------|---------|
| [edge-tts](https://pypi.org/project/edge-tts/) | Microsoft Neural TTS (free, no API key needed) |
| [playwright](https://playwright.dev/python/) | Browser automation + video recording |
| [click](https://click.palletsprojects.com/) | CLI framework |
| [pydantic](https://docs.pydantic.dev/) | JSON schema validation |
| [rich](https://rich.readthedocs.io/) | Terminal formatting |
| **ffmpeg** (system) | Audio/video assembly, GIF generation |

## Tips

- Use `demo-recorder voices --language en` to browse available voices
- Set `wait_after` to 5000+ ms after login clicks to allow session establishment
- Use `button:has-text('...')` selectors for buttons
- Set `"narration": ""` for silent steps (no audio, no subtitle)
- Use `--skip-gif` to speed up recording when you don't need the GIF preview
- Viewport `1920x1080` produces HD output; `1280x720` is faster and smaller

## License

MIT
