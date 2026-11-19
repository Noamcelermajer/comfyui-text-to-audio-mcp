# Sound Forge - local text-to-audio game sounds for Claude, Codex and any MCP client

**Turn a sentence into a game-ready sound on your own GPU.** Free, private and offline:
sound effects, seamless ambience loops, music stingers, looping background music and
character voice lines, delivered as trimmed, loudness-normalised `.wav` / `.ogg` files and
driven by your coding agent or the command line.

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MCP server](https://img.shields.io/badge/MCP-server-blueviolet)](https://modelcontextprotocol.io)
[![Agent skill](https://img.shields.io/badge/Agent%20Skill-SKILL.md-orange)](skills/sound-forge/SKILL.md)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-0.45%2B-informational)](https://github.com/comfyanonymous/ComfyUI)

> "make a heavy wooden door slam for the crypt level" &rarr; your agent generates four takes,
> keeps the one that best matches the prompt, trims it, makes it mono, normalises it and
> checks it - about two seconds later.

Sister project of [Asset Forge](https://github.com/Noamcelermajer/comfyui-text-to-3d-mcp)
(text to 3D models); both follow the same profile / preset / skill design.

**Why Sound Forge**

- **No credits, no cloud.** Everything runs on your own NVIDIA card, as often as you like.
- **Game-ready, not just generated.** Every file is trimmed, looped when it should loop
  (equal-power crossfade, cut to whole bars for music), converted to mono or stereo,
  normalised to a loudness target with a peak cap, and checked for silence, clipping,
  gaps and DC offset.
- **Best of N.** Several takes per call, ranked by how well they match the prompt (LAION
  CLAP); the others are kept so you can swap.
- **Characters keep their voice.** A voice is designed once from a description, saved,
  and cloned for every later line.
- **Fast / standard / max presets** and **hardware tiers** (8 / 12 / 16 / 24 GB) chosen
  automatically.
- **Consistent palette.** Style presets (`retro_8bit`, `cartoon`, `realistic`,
  `dark_fantasy`, `sci_fi`) or a per-game `soundforge.json`.
- **Swap models without code.** Each kind of sound is a small JSON profile around a
  ComfyUI graph.

## What it makes

| Profile | For | Model | Output |
| :--- | :--- | :--- | :--- |
| `sfx` | impacts, footsteps, weapons, spells, pickups, UI | Stable Audio 3 Small-SFX | mono, trimmed, -16 LUFS |
| `ambience` | forest, rain, cave, tavern, engine room | Stable Audio 3 Small-SFX | stereo, seamless loop, -24 LUFS |
| `stinger` | level up, victory, game over, item found | Stable Audio 3 Small-Music | stereo, -16 LUFS |
| `music_loop` | exploration, combat, town, menu | ACE-Step 1.5 (turbo) | stereo, loop cut to whole bars, -18 LUFS |
| `music_track` | title theme, credits, cutscene | ACE-Step 1.5 (turbo) | stereo, fades out, -18 LUFS |
| `voice` | dialogue, barks, narration | Qwen3-TTS 1.7B (design + clone) | mono, trimmed, -18 LUFS |

Presets: `fast` (one take, fewer steps), `standard` (default), `max` (Stable Audio 3
Medium or more takes). Short hits come out quieter than -16 LUFS: the peak is capped at
-1 dBFS rather than clipped.

## Measured

RTX 5080 16 GB, standard preset, seed 1234, models already loaded (the first call of a
session adds 10-20 s while weights load). VRAM is the whole GPU, including what ComfyUI
already had cached.

| Job | Result | Time | GPU memory |
| :--- | :--- | ---: | ---: |
| `sfx` door slam, 4 takes | 0.99 s, -19.8 LUFS | 20 s cold / ~1-2 s warm | 6.6 GB |
| `sfx` coins in a pouch, 4 takes | 1.08 s, -18.8 LUFS | 1.4 s | 5.7 GB |
| `sfx` fire spell, 4 takes | 1.48 s, -18.3 LUFS | 1.0 s | 5.6 GB |
| `ambience` cave, 3 takes | 28.1 s seamless loop, -24.8 LUFS | 3.3 s | 5.7 GB |
| `stinger` level-up, 4 takes | 4.1 s, -16.0 LUFS | 1.7 s | 6.0 GB |
| `voice` design a character voice | saved reference clip | ~20 s | 11.9 GB (first line only) |
| `voice` line 1 / line 2 (cloned) | 3.9 s / 4.3 s, -18.0 LUFS | 9.8 s / 9.5 s | 8.5 GB |
| `music_loop` 60 s | *being measured* | | |

Every job passed its checks. You cannot judge audio from numbers: listen to the results
(`tests/smoke_test.py` writes them to `tests/results/`).

## Requirements

- NVIDIA GPU with 8 GB of VRAM or more (16 GB tested), Windows or Linux
- ComfyUI 0.45 or newer (portable build is fine) and git
- About 35 GB of free disk for the default models (26 GB download), 60 GB with `--all`

| VRAM | What you get |
| :--- | :--- |
| 8 GB | Everything at `standard`. Music makes one take at a time; the voice model unloads after each line. |
| 12 GB | Everything, including the `max` presets with Stable Audio 3 Medium. |
| 16 GB | Everything (reference machine). |
| 24 GB+ | Room for the optional ACE-Step XL music model and its 4B planner. |

Only the 16 GB row has been measured.

## Install

The easiest way: paste [SETUP_PROMPT.md](SETUP_PROMPT.md) into Claude Code or Codex. By hand:

```
git clone https://github.com/Noamcelermajer/comfyui-text-to-audio-mcp SoundForge
cd SoundForge
python forge.py setup        # node pack + models for this GPU (--dry-run to preview, --all for the optional ones)
python forge.py doctor       # every profile should be "ready": true
python forge.py connect      # registers the MCP server and the skill for Claude and Codex
```

Sound Forge finds ComfyUI next to it or through `SOUNDFORGE_COMFY`, starts it when needed,
and hands over to ComfyUI's Python for the audio libraries. Full unattended instructions
for agents: [AGENTS.md](AGENTS.md).

## Use

From an agent: just ask ("make an ambience loop for a rainy harbour at night"). The skill
tells it which profile, length and prompt style to use. The MCP server has 7 tools:
`list_profiles`, `generate_sound`, `design_voice`, `get_job`, `check_audio`, `models`,
`forge_status`.

From the command line (every command prints one JSON object):

```
python forge.py sound door_slam "Heavy wooden door slamming shut in a stone hall, deep thud with a short echo" -p sfx --set duration=3
python forge.py sound cave "Damp cave interior, slow water drips, low wind rumble" -p ambience --project ../MyGame
python forge.py sound explore "Calm fantasy exploration, acoustic guitar, soft strings, flute" -p music_loop --set bpm=90 --set keyscale="D major"
python forge.py voice grave_keeper "An old man with a deep gravelly voice, slow and weary"
python forge.py sound keeper_01 "Who goes there? The graveyard is closed after dark." -p voice --voice grave_keeper --set emotion="suspicious"
python forge.py check some_file.wav
python forge.py batch jobs.json
```

Exit code 0 = ok, 2 = written but failed its check (see `problems`), 1 = error.

## Customising

- **Per game:** `python forge.py init <game folder>` writes a `soundforge.json` with the
  output folder, voices folder, style and per-profile settings.
- **Per call:** `--set key=value` / `params` (`duration`, `candidates`, `loudness`,
  `format=ogg`, `sample_rate=48000`, `loop`, `bpm`, ...). `forge.py profiles` explains
  every parameter.
- **New profile:** a JSON file in `profiles/user/` or the game's `soundforge_profiles/`
  that `extends` an existing one.
- **New model:** add it to `models/catalog.json` and write a profile around a ComfyUI API
  graph in `graphs/`.

Settings are layered: profile, hardware tier, project, preset, style, call; the tier's
limits are applied last so a call cannot run an 8 GB card out of memory.

## Licences

Sound Forge's code is MIT. The models are not: Stable Audio 3 uses the **Stability AI
Community License** (free for individuals and organisations under $1M annual revenue; you
own the outputs), ACE-Step 1.5 is MIT with commercial use of outputs allowed, Qwen3-TTS
and CLAP are Apache 2.0. Details in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Only clone voices you have the right to use.
