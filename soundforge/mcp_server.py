"""MCP server over stdio (JSON-RPC 2.0, one message per line). No dependencies.

Generation takes minutes, which is longer than most clients wait for a tool call,
so generate_sound and design_voice start a background job and wait only `wait_seconds`; `get_job`
picks the result up later. One job runs at a time (one GPU).
"""
import json
import os
import queue
import sys
import threading
import time
import traceback
import uuid

from . import comfy, models, pipeline, profiles
from .config import load_machine

PROTOCOL = "2025-06-18"
_out_lock = threading.Lock()
_jobs, _queue = {}, queue.Queue()


def _send(msg):
    with _out_lock:
        sys.__stdout__.write(json.dumps(msg) + "\n")
        sys.__stdout__.flush()


def _worker():
    while True:
        job = _jobs[_queue.get()]
        job["status"], job["started"] = "running", time.time()
        try:
            job["result"] = job["fn"]()
            job["status"] = job["result"].get("status", "ok")
        except Exception as e:
            job.update(status="error", error=f"{type(e).__name__}: {e}")
        job["finished"] = time.time()


def _submit(kind, name, fn, wait_seconds):
    job_id = uuid.uuid4().hex[:8]
    _jobs[job_id] = {"id": job_id, "kind": kind, "name": name, "status": "queued", "fn": fn, "created": time.time()}
    _queue.put(job_id)
    return _job_view(job_id, wait_seconds)


def _job_view(job_id, wait_seconds=0):
    if job_id not in _jobs:
        raise ValueError(f"no job '{job_id}' (jobs are forgotten when the server restarts; the files and <name>.json stay on disk)")
    job = _jobs[job_id]
    deadline = time.time() + max(0, min(float(wait_seconds or 0), 55))
    while job["status"] in ("queued", "running") and time.time() < deadline:
        time.sleep(1)
    view = {k: job[k] for k in ("id", "kind", "name", "status") if k in job}
    images = []
    if job["status"] in ("queued", "running"):
        view["elapsed_s"] = round(time.time() - job.get("started", job["created"]))
        view["queue_position"] = sum(1 for j in _jobs.values() if j["status"] == "queued" and j["created"] <= job["created"])
        view["next"] = f"call get_job with id '{job_id}' and wait_seconds 50 until status is no longer queued/running"
    elif "error" in job:
        view["error"] = job["error"]
    else:
        view["result"] = job["result"]
    return view, images


# ----------------------------------------------------------------------------- tools

def t_status(a):
    m = load_machine()
    return {"gpu": m["gpu"], "ram_gb": m["ram_gb"], "vram_tier": m["tier"], "comfyui_running": comfy.is_up(),
            "comfyui": m["comfy_root"],
            "jobs": [{k: j[k] for k in ("id", "kind", "name", "status")} for j in _jobs.values()][-10:],
            "project": profiles.load_project(a.get("project_dir")) if a.get("project_dir") else None}, []


def t_list_profiles(a):
    return {"profiles": profiles.list_profiles(a.get("project_dir")),
            "styles": profiles.list_styles(a.get("project_dir")),
            "voices": [{k: v.get(k) for k in ("voice", "description", "reference")} for v in pipeline.list_voices(a.get("project_dir"))]}, []


def t_generate_sound(a):
    fn = lambda: pipeline.generate_sound(a.get("profile", "sfx"), a["name"], a.get("prompt"), a.get("project_dir"), a.get("out_dir"),
                                         a.get("seed"), a.get("style", ""), a.get("params"), a.get("force", False),
                                         a.get("preset", "standard"), a.get("style_preset"), a.get("lyrics"), a.get("voice"),
                                         a.get("voice_description"))
    return _submit("sound", a["name"], fn, a.get("wait_seconds", 50))


def t_design_voice(a):
    fn = lambda: pipeline.design_voice(a["voice"], a.get("voice_description"), a.get("project_dir"), a.get("seed"),
                                       a.get("language", "Auto"), a.get("force", False))
    return _submit("voice", a["voice"], fn, a.get("wait_seconds", 50))


def t_get_job(a):
    return _job_view(a["id"], a.get("wait_seconds", 50))


def t_check_audio(a):
    return pipeline.check_file(a["path"], a.get("kind", "sfx")), []


def t_models(a):
    if a.get("install"):
        return {"installed": models.install(a["install"])}, []
    return models.report(a.get("project_dir")), []


_PROJECT = {"type": "string", "description": "Absolute path of the game project. Its soundforge.json (style, output folder, voices folder, per-profile settings) is applied and files are written into its output folder."}
_WAIT = {"type": "number", "description": "Seconds to wait for the result before returning a job id (max 55, default 50)."}

TOOLS = {
    "forge_status": (t_status, "Hardware, whether ComfyUI is running, recent jobs, and a project's settings.",
                     {"project_dir": _PROJECT}, []),
    "list_profiles": (t_list_profiles, "The sound profiles (sfx, ambience, stinger, music_loop, music_track, voice) with their parameters, presets and prompt guides; the style presets; and the saved character voices. Call this first.",
                      {"project_dir": _PROJECT}, []),
    "generate_sound": (t_generate_sound,
                       "Text -> game-ready audio file (.wav/.ogg): makes several takes, keeps the one that best matches the prompt, trims, loops if the profile loops, normalises loudness and checks it. Effects take seconds, music a minute or more. Returns the result, or a job id to poll with get_job.",
                       {"profile": {"type": "string", "description": "sfx (default), ambience, stinger, music_loop, music_track or voice."},
                        "name": {"type": "string", "description": "Asset id; becomes the file name."},
                        "prompt": {"type": "string", "description": "What it sounds like (see the profile's prompt_guide). For voice: exactly the words to speak."},
                        "preset": {"type": "string", "enum": ["fast", "standard", "max"],
                                   "description": "fast = one quick take; standard = the profile's tuned default; max = the biggest model and the most takes."},
                        "style_preset": {"type": "string", "description": "Style id from list_profiles['styles'] (retro_8bit, cartoon, realistic, dark_fantasy, sci_fi). Defaults to the project's."},
                        "style": {"type": "string", "description": "Extra wording added to the prompt after the style preset and the project's style."},
                        "lyrics": {"type": "string", "description": "Music only: '[Instrumental]' (default) or lyrics with [Verse]/[Chorus] tags."},
                        "voice": {"type": "string", "description": "Voice only: a character id. Reuses that saved voice; if it does not exist yet it is created from voice_description."},
                        "voice_description": {"type": "string", "description": "Voice only: who speaks and how they sound (age, gender, accent, timbre, pace)."},
                        "params": {"type": "object", "description": "Profile parameters to override, e.g. {\"duration\": 2, \"candidates\": 6, \"bpm\": 90, \"emotion\": \"angry\", \"format\": \"ogg\"}. list_profiles shows each profile's parameters."},
                        "seed": {"type": "integer", "description": "Fix the result; change it for a different take."},
                        "project_dir": _PROJECT,
                        "out_dir": {"type": "string", "description": "Output folder; overrides the project's."},
                        "force": {"type": "boolean", "description": "Regenerate even if a file with the same name and settings exists."},
                        "wait_seconds": _WAIT}, ["name", "prompt"]),
    "design_voice": (t_design_voice, "Create (or, with force, replace) a named character voice from a description. Saves a reference clip that every later voice line with this `voice` id reuses.",
                     {"voice": {"type": "string", "description": "Character id, e.g. grave_keeper."},
                      "voice_description": {"type": "string", "description": "Who speaks and how they sound."},
                      "language": {"type": "string", "description": "Auto (default), English, Chinese, Japanese, Korean, French, German, Spanish, Portuguese, Russian or Italian."},
                      "seed": {"type": "integer"}, "force": {"type": "boolean"}, "project_dir": _PROJECT, "wait_seconds": _WAIT},
                     ["voice", "voice_description"]),
    "get_job": (t_get_job, "Status or result of a generate_sound / design_voice job.",
                {"id": {"type": "string"}, "wait_seconds": _WAIT}, ["id"]),
    "check_audio": (t_check_audio, "Measure any audio file: length, peak, loudness (LUFS), clipping, silence, and problems.",
                    {"path": {"type": "string", "description": "Absolute path of the file."},
                     "kind": {"type": "string", "description": "sfx, ambience, music or voice (selects the checks)."}}, ["path"]),
    "models": (t_models, "Which model files each profile and preset needs, what is missing, and advice for this GPU. Pass install=[names] to download catalog items (large; ask the user first).",
               {"project_dir": _PROJECT, "install": {"type": "array", "items": {"type": "string"}, "description": "Catalog file names or repo ids to download."}}, []),
}


def _handle(msg):
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        version = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL
        return {"protocolVersion": version, "capabilities": {"tools": {}},
                "serverInfo": {"name": "sound-forge", "version": "0.1.0"},
                "instructions": "Local game audio generation: sound effects, ambience loops, stingers, music and character voice lines. "
                                "Start with list_profiles. Pass project_dir so the project's style, output and voices folders apply. "
                                "Longer jobs return a job id: poll get_job."}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [{"name": n, "description": d, "inputSchema": {"type": "object", "properties": props, "required": req}}
                          for n, (_f, d, props, req) in TOOLS.items()]}
    if method == "tools/call":
        p = msg.get("params") or {}
        name, args = p.get("name"), p.get("arguments") or {}
        if name not in TOOLS:
            raise LookupError(f"unknown tool {name}")
        try:
            data, images = TOOLS[name][0](args)
            return {"content": [{"type": "text", "text": json.dumps(data, indent=1)}, *images], "isError": False}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}
    if mid is None:
        return None  # a notification we do not need
    raise LookupError(f"method not found: {method}")


def serve():
    sys.stdout = sys.stderr  # nothing but protocol messages may reach the real stdout
    threading.Thread(target=_worker, daemon=True).start()
    pending = []
    for line in sys.stdin:
        line = line[line.find("{"):].strip() if "{" in line else ""  # tolerate a byte-order mark
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if "method" not in msg:
            continue
        mid = msg.get("id")

        def run(msg=msg, mid=mid):
            try:
                result = _handle(msg)
                if mid is not None:
                    _send({"jsonrpc": "2.0", "id": mid, "result": result})
            except LookupError as e:
                if mid is not None:
                    _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": str(e)}})
            except Exception as e:
                traceback.print_exc(file=sys.stderr)
                if mid is not None:
                    _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}})

        if msg["method"] == "tools/call":
            # tool calls may block while waiting on a job; keep the reader loop free
            t = threading.Thread(target=run, daemon=True)
            t.start()
            pending.append(t)
        else:
            run()
    for t in pending:  # stdin closed: let calls in flight answer before exiting
        t.join(timeout=60)
