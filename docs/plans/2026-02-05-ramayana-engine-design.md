# Ramayana Engine — Design Document

**Date**: 2026-02-05
**Status**: Approved
**Project**: ramayana-engine — Scene-driven 2D animation engine for narrated Valmiki Ramayana episodes

---

## Summary

A tool that produces narrated 2D animated video episodes of Valmiki's original Ramayana from declarative JSON scripts. Episode scripts define scenes, character positions, animations, camera movements, narration, music, and sound effects. The engine renders scenes in a PixiJS-based web app, captures them with Playwright, and assembles the final video with multi-layer audio using ffmpeg.

**MVP**: A single 4-5 minute episode — "The Breaking of Shiva's Bow" (Sita Swayamvar).

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Visual format | Simple 2D character animation | Characters with movements on scene backgrounds. Most engaging. |
| Scale | Single episode MVP | Validate pipeline before scaling to series. |
| Narration language | English | Best TTS quality, widest audience. |
| MVP scene | Sita Swayamvar | Clear three-act structure, limited scene changes, natural "Episode 1". |
| Tech stack | HTML5 + PixiJS + Playwright | Reuses demo-recorder concepts (TTS, Playwright capture, ffmpeg assembly). |
| Art style | Indian miniature painting | Profile-view characters, flat colors, ornate details. Authentic to source. |
| Asset creation | AI backgrounds + commissioned character sprites | AI handles environments well. Characters need consistency from a human artist. |
| Audio | Full design: narration + background music + SFX | Most immersive experience. Three-layer audio mix. |

---

## Architecture

### Core Pipeline

```
Episode Script (JSON)
       │
       ▼
┌─────────────────┐     ┌──────────────────┐
│  Scene Renderer  │     │  Audio Pipeline   │
│  (PixiJS + Web)  │     │  (Edge TTS +      │
│                  │     │   Music + SFX)    │
│  - Backgrounds   │     │                  │
│  - Characters    │     │  - Narration     │
│  - Animations    │     │  - Background    │
│  - Camera moves  │     │    music         │
│  - Transitions   │     │  - Sound effects │
└────────┬─────────┘     └────────┬─────────┘
         │                        │
         ▼                        ▼
   Playwright captures      ffmpeg mixes all
   browser viewport         audio layers
         │                        │
         └──────────┬─────────────┘
                    ▼
             Final Assembly (ffmpeg)
             MP4 + SRT subtitles
```

### Relationship to demo-recorder

Ramayana-engine is a **new project** that reuses the same concepts:
- **Edge TTS** — narration generation
- **Playwright** — viewport capture (recording a PixiJS canvas instead of a website)
- **ffmpeg** — video + multi-layer audio assembly (extended for 3-layer mixing)
- **JSON script** — declarative episode definition (richer schema with scenes, beats, camera, audio cues)

Key difference: demo-recorder drives a real website. Ramayana-engine drives a custom PixiJS scene renderer.

---

## Episode Script Format

```json
{
  "episode": {
    "id": "ep01_sita_swayamvar",
    "title": "The Breaking of Shiva's Bow",
    "duration_target": "5-7 min",
    "resolution": { "width": 1920, "height": 1080 },
    "narration": {
      "voice": "en-US-GuyNeural",
      "rate": "-5%"
    }
  },

  "assets": {
    "backgrounds": {
      "court_hall": "assets/bg/janaka_court.png",
      "court_hall_depth": "assets/bg/janaka_court_layers.json"
    },
    "characters": {
      "rama": "assets/chars/rama/spritesheet.json",
      "sita": "assets/chars/sita/spritesheet.json",
      "janaka": "assets/chars/janaka/spritesheet.json",
      "vishwamitra": "assets/chars/vishwamitra/spritesheet.json",
      "king_generic": "assets/chars/king_generic/spritesheet.json"
    },
    "props": {
      "shiva_bow": "assets/props/shiva_bow.png",
      "garland": "assets/props/garland.png"
    },
    "music": {
      "court_ambient": "assets/audio/court_ambient.mp3",
      "tension_build": "assets/audio/tension_drums.mp3",
      "triumph": "assets/audio/triumph_sitar.mp3"
    },
    "sfx": {
      "bow_crack": "assets/audio/sfx/bow_crack.wav",
      "crowd_gasp": "assets/audio/sfx/crowd_gasp.wav",
      "crowd_cheer": "assets/audio/sfx/crowd_cheer.wav",
      "footsteps": "assets/audio/sfx/footsteps.wav"
    }
  },

  "scenes": [
    {
      "id": "scene_01_court_intro",
      "background": "court_hall",
      "music": { "track": "court_ambient", "volume": 0.3, "fade_in": 2000 },
      "camera": { "x": 0, "y": 0, "zoom": 1.0 },
      "characters_on_stage": [
        { "id": "janaka", "position": { "x": 960, "y": 500 }, "state": "sitting_throne" },
        { "id": "king1", "ref": "king_generic", "position": { "x": 300, "y": 600 }, "state": "standing" }
      ],
      "props_on_stage": [
        { "id": "shiva_bow", "position": { "x": 960, "y": 650 }, "scale": 1.2 }
      ],
      "beats": [
        {
          "narration": "In the grand court of King Janaka...",
          "actions": [
            { "type": "camera_pan", "to": { "x": 100, "y": 0 }, "duration": 3000 }
          ]
        }
      ]
    }
  ]
}
```

### Key Concepts

- **Scenes** — one background + characters + props. Scene change = new background + transition.
- **Beats** — atomic unit within a scene. Each has narration + simultaneous actions. Beat duration driven by narration length.
- **Character state** — named animation from sprite sheet (idle, walking, lifting, etc.).
- **Actions** — camera_pan, camera_zoom, camera_shake, character_move, character_state, sfx, music_change, transition.

---

## Scene Renderer (PixiJS Engine)

### Module Structure

```
renderer/src/engine/
├── SceneManager.ts     # Loads scenes, manages transitions
├── Timeline.ts         # Drives beats sequentially, emits timing events
├── CharacterSprite.ts  # Loads sprite sheets, plays named animations
├── Background.ts       # Parallax layer rendering (2-3 depth layers)
├── Camera.ts           # Pan, zoom, shake on the PixiJS stage
├── PropManager.ts      # Static/animated props on stage
├── TransitionFX.ts     # Fade, dissolve, wipe between scenes
└── AudioCueEmitter.ts  # Emits SFX/music cue timestamps (no audio playback)
```

### How It Works

1. `main.ts` loads episode JSON, preloads all sprite sheets and backgrounds
2. `SceneManager` sets up background layers, places characters and props
3. `Timeline` iterates beats — executes actions concurrently, waits for narration duration, advances
4. `AudioCueEmitter` logs wall-clock timestamps for every SFX/music cue (used later by ffmpeg)
5. Renderer exposes `window.setBeatDurations()`, `window.startPlayback()`, `window.playbackComplete` for Playwright

### Character Animation

Sprite sheets as texture atlases, 3-4 frames per pose:
- idle (breathing loop), walking (8-frame cycle), action poses, speaking (mouth open/close)
- Played at 8-12 fps for miniature painting aesthetic

### Camera System

- Pan: GSAP tween on stage x/y
- Zoom: GSAP tween on stage scale toward target point
- Shake: Quick oscillation for dramatic moments
- Parallax: Background layers move at different rates during pan

---

## Recording + Audio Assembly Pipeline

### 5-Phase Pipeline

```
Phase 1: Parse script → extract narration texts + audio cues
Phase 2: Generate TTS per beat (Edge TTS) → measure durations
Phase 3: Send durations to renderer → Playwright records canvas
Phase 4: Assemble 3-layer audio (narration + music + SFX at timestamps)
Phase 5: Merge video + audio + subtitles → final MP4
```

### Audio Mixing (3 Layers)

```
Layer 1: Narration    ──|clip1|────|clip2|──|clip3|────────|clip4|──
Layer 2: Music        ──|court_ambient (looping)──|tension──|triumph──
Layer 3: SFX          ────────|gasp|──────────────|crack!|──|cheer|──
```

Uses ffmpeg `adelay` filters to position clips at wall-clock timestamps, `amix` to combine layers with per-layer volume control.

### Subtitle Styling

Serif font (Noto Serif / EB Garamond), warm color, gentle shadow — fits classical storytelling tone.

---

## Project Structure

```
ramayana-engine/
├── package.json
├── pyproject.toml
├── requirements.txt
├── renderer/                       # PixiJS scene engine (TypeScript)
│   ├── index.html
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── src/
│       ├── main.ts
│       └── engine/ (7 modules)
├── pipeline/                       # Python recording + assembly
│   ├── cli.py
│   ├── script_parser.py
│   ├── narration.py
│   ├── recorder.py
│   ├── audio_mixer.py
│   ├── assembler.py
│   └── models.py
├── assets/
│   ├── backgrounds/
│   ├── characters/ (5 sprite sheets)
│   ├── props/
│   └── audio/
│       ├── music/ (3 tracks)
│       └── sfx/ (5 clips)
├── episodes/
│   └── ep01_sita_swayamvar.json
└── output/
```

### CLI

```bash
ramayana-engine preview episodes/ep01.json     # Browser preview (hot-reload)
ramayana-engine render episodes/ep01.json      # Full render pipeline
ramayana-engine voices --language en            # List TTS voices
```

---

## MVP Episode — "The Breaking of Shiva's Bow"

### Scene Breakdown

| Scene | Beats | ~Duration | Description |
|-------|-------|-----------|-------------|
| 1. Janaka's Court | 3 | 45s | Grand court, kings assembled, challenge introduced. Camera pan. Music: court ambient. |
| 2. The Challenge | 2 | 30s | Janaka gestures to bow. Close-up on divine bow. Its origin described. |
| 3. Kings Attempt and Fail | 3 | 40s | Montage of kings trying and failing. Crowd murmurs. Music: tension drums. |
| 4. Rama Enters | 3 | 45s | Vishwamitra nods. Rama walks calmly. Court falls silent. Sita watches. Music softens. |
| 5. The Breaking | 4 | 50s | Rama lifts bow effortlessly. Draws string. Bow snaps. Camera shake. SFX: bow_crack, crowd_gasp. |
| 6. Sita's Garland | 3 | 40s | Sita descends with garland. Places it on Rama. Court celebrates. Music: triumph. SFX: crowd_cheer. |
| **Total** | **18** | **~4-5 min** | |

### Characters Required

| Character | Poses | Notes |
|-----------|-------|-------|
| Rama | idle, walking, lifting, drawing_bow, triumphant, speaking | Most poses |
| Sita | idle, walking, garlanding, watching, speaking | Scenes 4-6 |
| Janaka | sitting_throne, standing, gesturing, rejoicing | Mostly seated |
| Vishwamitra | standing, nodding, speaking | Minimal |
| King (generic) | standing, approaching, straining, failing, retreating | Reused with color tinting |

---

## Asset Creation Strategy

| Asset | Count | Method | Timeline | Cost |
|-------|-------|--------|----------|------|
| Character sprites | 5 sheets | Commission artist (Fiverr/Upwork) | 1-2 weeks | $150-300 |
| Backgrounds | 3 images | Stable Diffusion + miniature painting LoRA + parallax layer split | 1-2 days | Free |
| Music | 3 tracks | Royalty-free libraries + AI generation (Suno/Udio) | 1 day | Free |
| Sound effects | 5 clips | freesound.org (CC0/CC-BY) | 1 hour | Free |

### Sprite Sheet Spec for Artist

- Style: Indian miniature painting (Rajput/Pahari)
- View: Profile or three-quarter
- Frame size: 512x512, transparent background
- 3-4 frames per pose (subtle animation loops)
- Palette: ochre, vermillion, gold, deep blue, forest green

### Background Generation

- Stable Diffusion XL + miniature painting LoRA
- Prompt: `"Indian miniature painting style, [scene], ornate details, flat colors, gold accents, Rajput Pahari art, no characters, 1920x1080"`
- Split into 2-3 parallax layers in GIMP/Photoshop

---

## Implementation Roadmap

```
Week 1:  ████ Phase 1: Skeleton Renderer (PixiJS + static scenes)
         ████ Phase 2: Timeline + Camera + character states
         ████ Commission sprites (parallel, start day 1)

Week 2:  ████ Phase 3: Python pipeline (TTS, Playwright recording, ffmpeg assembly)
         ████ Phase 4: AI backgrounds + music/SFX sourcing (parallel)

Week 3:  ████ Phase 5: Scene transitions, parallax, visual polish
         ████ Integrate real assets as they arrive

Week 4:  ████ Phase 6: Write episode script, iterate, final render
```

### Phase Details

1. **Skeleton Renderer** — PixiJS app loads scene JSON, displays background + positioned sprites. Placeholder assets (colored shapes).
2. **Timeline + Camera** — Beats play in sequence. Camera pans/zooms. Characters change states. AudioCueEmitter logs timestamps.
3. **Python Pipeline** — End-to-end: parse script → TTS → Playwright record → 3-layer audio mix → final MP4. Test with placeholders.
4. **Real Assets** — Commission arrives, backgrounds generated, audio sourced. Drop into renderer.
5. **Polish** — Transitions, parallax, GSAP easing, subtitle styling, animation FPS tuning.
6. **Episode Script** — Write the full 18-beat Swayamvar script. Iterate render → watch → adjust. 5-10 iterations expected.

---

## Dependencies

### Renderer (TypeScript)
- PixiJS 8 — 2D WebGL rendering
- GSAP — animation tweening
- Vite — dev server + build

### Pipeline (Python)
- edge-tts — TTS narration
- playwright — browser recording
- pydantic — script schema validation
- click + rich — CLI
- ffmpeg (system) — audio/video assembly

---

## Future Expansion (Post-MVP)

- More episodes covering key Ramayana moments (20-30 episode series)
- Hindi narration option with Sanskrit shloka recitation
- Lip sync system (mouth sprite frames timed to audio phonemes)
- YouTube/social media export presets (shorts, reels)
- Episode template system — reusable scene layouts for faster production
