# Sound Forge - instructions for AI agents

This file is for an AI agent (Claude, Codex, or any other) asked to install or use Sound
Forge. Everything here can be done without asking a human, except where it says to ask.
Every `forge.py` command prints one JSON object on stdout; read it to decide the next step.

- **Installing?** Follow [Install](#install-unattended) from top to bottom.
- **Already installed and asked to make a sound?** Read [`skills/sound-forge/SKILL.md`](skills/sound-forge/SKILL.md).
- **Changing profiles or adding a model?** Read the "Customising" section of [`README.md`](README.md).

## What gets installed

| Layer | What | Installed by |
| :--- | :--- | :--- |
| Base | ComfyUI 0.45 or newer with CUDA PyTorch; git | you, with the commands below (skipped when present) |
| Node pack | ComfyUI-Qwen-TTS (voice lines), listed in `models/catalog.json` under `node_packs` | `forge.py setup` |
| Models | about 26 GB by default; up to 54 GB with `--all` (adds Stable Audio 3 Medium and the ACE-Step XL models), listed in `models/catalog.json` | `forge.py setup` |
| Connector | MCP server entry and skill for Claude and Codex | `forge.py connect` |

Sound effects, ambience, stingers and music use nodes built into ComfyUI 0.45; only voice
lines need the node pack. Requirements: an NVIDIA GPU with at least 8 GB of VRAM, about
35 GB of free disk space (60 GB for `--all`), Windows or Linux.

## Install (unattended)

Run the steps in order. Each one is safe to repeat; anything already present is skipped.

### 1. Clone

Clone this repository and `cd` into it. Use any Python 3.10+ to run `forge.py`; it hands
over to ComfyUI's own Python, which has the audio libraries it needs.

### 2. Run setup and act on its answer

```
python forge.py setup
```

| `status` | Exit code | Meaning and what to do |
| :--- | :--- | :--- |
| `ok` | 0 | Node pack and models are in place. Go to step 3. |
| `blocked` | 3 | Base software is missing, ComfyUI is too old, or the disk is too full. Run the commands in `manual_steps[].commands` (or free space), then run `setup` again. |
| `partial` | 3 | Something failed to install. Each failed item carries its own error and, where one exists, a `manual` command. Fix those and run `setup` again. |

- **ComfyUI not found.** If ComfyUI is already installed somewhere, set the environment
  variable `SOUNDFORGE_COMFY` to its folder (the one containing `main.py`) and run `setup`
  again - do not install a second copy. Search the usual places first. Only if none
  exists, install it (commands in `manual_steps`).
- **Restart ComfyUI** if `setup` reports `restart_comfyui`: new node packs load only at
  start-up. Sound Forge starts ComfyUI again by itself when it next needs it.
- Flags: `--dry-run` lists what would be installed and the download size; `--all` also
  installs the optional larger models (Stable Audio 3 Medium for the `max` presets, ACE-Step
  XL) that fit this GPU; `--skip-models` / `--skip-nodes` do one half; `--pinned` checks out
  the node-pack commit Sound Forge was tested with.

### 3. Verify

```
python forge.py doctor
```

Every entry under `profiles` must show `"ready": true`, an empty `missing` list and (when
ComfyUI is running) an empty `missing_nodes` list. `missing` not empty: run `setup` again or
`python forge.py models --install <name> ...`. `missing_nodes` not empty: read the import
error in ComfyUI's start-up log; usually the node pack's requirements did not install.

### 4. Connect the agent

```
python forge.py connect
```

Registers the MCP server and installs the skill for Claude and Codex at user level, backing
up each config file it edits. `--claude` or `--codex` for one, `--project <dir>` for a
single project, `--dry-run` to preview. A new agent session is needed before the tools appear.

Any other MCP client: a stdio server with command `python` and arguments
`["<this folder>/forge.py", "mcp"]`.

### 5. Prove it works

```
python forge.py sound setup_test "Heavy wooden door slamming shut in a stone hall, deep thud with a short echo" -p sfx --set duration=3
```

Success is `"status": "ok"`, an empty `problems` list, and a `file` whose `audio.seconds`
is between 0.3 and 3 and whose `audio.loudness_lufs` is between -20 and -16 (short hits stay quieter than -16 because the peak is capped at -1 dB). The first run is slower
while weights load.

### 6. Report

Tell the user what was already present, what was installed, how many GB were downloaded,
which config files `connect` edited, the test result and its file path (ask them to listen
to it), and anything still missing.

## Rules while installing

- Never delete, replace or downgrade existing models, node packs or Python packages.
- Never change the installed PyTorch of an existing ComfyUI. `setup` pins it while
  installing the node pack's requirements; if something still wants to change it, stop and report.
- Install Python packages only into ComfyUI's interpreter (`comfy_python` in `machine.json`).
- Do not edit `graphs/` to get past an error; settings belong in profiles.
- Do not work around the disk-space check by deleting the user's files.
- Model licences: Stable Audio 3 uses the Stability AI Community License (free for
  individuals and organisations under $1M annual revenue). Tell the user this in the report.
