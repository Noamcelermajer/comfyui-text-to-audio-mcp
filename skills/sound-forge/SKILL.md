---
name: sound-forge
description: Generate game audio locally and for free - sound effects, UI sounds, seamless ambience loops, music stingers, looping background music and character voice lines - as game-ready .wav/.ogg files from a text prompt. Use whenever the user asks to create, generate, regenerate or fix a sound effect, SFX, ambience, soundtrack, music loop, jingle, voice line, dialogue or bark, or to check an audio file's loudness.
---

# Sound Forge

Sound Forge turns text into game-ready audio on this machine's GPU (ComfyUI underneath; it
is started automatically). Nothing is sent to a paid service. Every result is trimmed,
looped when it should loop, converted to mono or stereo as the use needs, loudness-normalised
and checked.

## How to call it

Prefer the **`sound-forge` MCP tools** when they are available:
`list_profiles`, `generate_sound`, `design_voice`, `get_job`, `check_audio`, `models`, `forge_status`.

Otherwise use the command line from the Sound Forge folder; every command prints one JSON object:

```
python forge.py profiles
python forge.py sound  <name> "<prompt>" -p sfx --project <game folder>
python forge.py sound  <name> "<style>" -p music_loop --set bpm=90 --project <game folder>
python forge.py voice  <character> "<who speaks and how they sound>" --project <game folder>
python forge.py sound  <name> "<words to speak>" -p voice --voice <character> --set emotion="angry" --project <game folder>
python forge.py check  <file.wav>
```

Exit code 0 = ok, 2 = finished but the result failed its check, 1 = error.

## Pick the profile

| Profile | For | Model | Output |
| :--- | :--- | :--- | :--- |
| `sfx` | one-shots: impacts, footsteps, weapons, spells, pickups, UI clicks | Stable Audio 3 Small-SFX | mono, trimmed, -16 LUFS |
| `ambience` | background beds: forest, rain, cave, tavern, engine room | Stable Audio 3 Small-SFX | stereo, seamless loop, -24 LUFS |
| `stinger` | short music cues: level up, victory, game over, item found | Stable Audio 3 Small-Music | stereo, -16 LUFS |
| `music_loop` | looping background music: exploration, combat, town, menu | ACE-Step 1.5 | stereo, loop cut to whole bars, -18 LUFS |
| `music_track` | music with an ending: title theme, credits, cutscene | ACE-Step 1.5 | stereo, fades out, -18 LUFS |
| `voice` | dialogue, barks, narration | Qwen3-TTS | mono, trimmed, -18 LUFS |

Each has three presets: `fast` (one quick take), `standard` (the default), `max` (bigger
model or more takes). Say which preset you used.

## Workflow

1. **Always pass the game project folder** (`project_dir` / `--project`). Its
   `soundforge.json` supplies the style, the output folder, the voices folder and
   per-profile settings, so a game's sounds stay consistent. If it has none, offer to
   create one (`forge.py init <dir>`).
2. **Write the prompt the way the profile's `prompt_guide` says** (`list_profiles` returns
   it). Describe only the sound - do not write "a sound effect of".
3. **Set the length.** `params.duration` in seconds: clicks and impacts 1-2, actions 3-6,
   ambience 20-60, music 30-120. Effects are trimmed to the sound afterwards.
4. **Longer jobs are asynchronous.** If `generate_sound` returns a job id, call `get_job`
   with `wait_seconds: 50` until the status is not `queued` or `running`. One job at a time.
5. **Report honestly.** You cannot hear the result. Report the file, its length, loudness
   and any `problems`, say that the user should listen to it, and mention the other takes
   kept in `.soundforge/<name>/` (`candidates`) in case the chosen one is wrong.

## Prompts

- **sfx**: source + material + space + how it evolves. "Heavy wooden door slamming shut
  in a stone hall, deep thud with a short echo". One sound per file - layer in the engine.
- **ambience**: the bed and the textures, no one-off events (they repeat audibly in a loop).
- **stinger**: instrument + gesture + mood. "Bright ascending harp and bell arpeggio, rewarding".
- **music**: genre, instruments, mood, era as the prompt; tempo and key as `bpm` and
  `keyscale` params. Instrumental by default; pass `lyrics` for a song.
- **voice**: `prompt` is exactly the words. Use `voice` (a character id) for any character
  with more than one line: the first call designs the voice from `voice_description`, later
  calls reuse it, so the character keeps one voice. Put the delivery in `params.emotion`
  ("whispering, scared", "shouting, furious"). Keep each line to one or two sentences.

## Style

For a consistent palette across a game, pass `style_preset` (`retro_8bit`, `cartoon`,
`realistic`, `dark_fantasy`, `sci_fi`) or set `style_preset` / `style` once in the
project's `soundforge.json`. The `style` text is appended to every prompt.

## When the result says `failed_check`

The file is written but should not be used as is. `problems` explains why.

| Problem | Fix |
| :--- | :--- |
| `silent` | Re-run with `force: true` and a new `seed`; make the prompt more concrete. |
| `distorted` | Re-run with a new `seed`; for music try `preset: "max"` (more takes). |
| `gappy` (ambience, music) | The model left long pauses. Describe a continuous bed ("steady", "constant"), re-run. |
| `too short after trimming` | The sound is quieter than its noise floor: re-run, or set `params.trim: false`. |

Same `name` + same settings returns the existing file; change a setting, the seed, or pass
`force: true` to make a new one.

## Customising

- Per project: `soundforge.json` (`style`, `style_preset`, `output_dir`, `voices_dir`,
  `profiles.<id>.params`, e.g. `{"music_loop": {"params": {"format": "ogg"}}}`).
- Per call: `params`, e.g. `{"duration": 2, "candidates": 6, "loudness": -20, "format": "ogg",
  "sample_rate": 48000}`. `list_profiles` lists every parameter with an explanation.
- New profile: a small JSON file in the project's `soundforge_profiles/` that `extends` one.
- Models and hardware: the `models` tool reports what each profile and preset needs and
  what is missing. Downloads are large - ask the user before installing.
- Licences: Stable Audio 3 is under the Stability AI Community License (free under $1M
  annual revenue; outputs are yours). ACE-Step 1.5 is MIT with commercial use of outputs
  allowed. Qwen3-TTS is Apache 2.0. Mention this if the user is shipping a commercial game.
