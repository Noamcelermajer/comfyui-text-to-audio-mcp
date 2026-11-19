"""The engine: run a profile, keep the best candidate, and make it game-ready.

generate_sound  text -> checked, loudness-normalised .wav/.ogg (effects, ambience, stingers,
                music, voice lines)
generate_batch  many sounds, grouped by model so weights load once per group

A voice line can name a `voice` (a character). The first time, the voice is designed
from `voice_description` and a neutral reference line is saved to <project>/voices/;
every later line for that character clones the reference, so the character keeps one voice.
"""
import hashlib
import json
import os
import random
import re
import shutil
import time
import uuid

from . import audio, comfy, profiles, score
from .config import FORGE_ROOT, log

OUT_SUBFOLDER = "soundforge"
REFERENCE_LINE = ("Well, here I am. This is how I sound when I talk normally - "
                  "not too loud, not too quiet. Are you ready? Then let us begin.")
_vram = {"group": None}


def safe_name(name):
    name = re.sub(r"[^A-Za-z0-9_\-]+", "_", str(name).strip()).strip("_")
    if not name:
        raise ValueError("name must contain letters or digits")
    return name


def out_dir_for(project_dir=None, out_dir=None):
    if out_dir:
        return os.path.abspath(out_dir)
    if project_dir:
        return os.path.abspath(os.path.join(project_dir, profiles.load_project(project_dir).get("output_dir", "assets/audio")))
    return os.path.join(FORGE_ROOT, "output")


def voices_dir(project_dir=None):
    if not project_dir:
        return os.path.join(FORGE_ROOT, "voices")
    return os.path.join(os.path.abspath(project_dir), profiles.load_project(project_dir).get("voices_dir", "voices"))


def _fill(value, ctx):
    """'{name}' alone keeps the value's type; inside a longer string it is formatted in."""
    if not isinstance(value, str):
        return value
    m = re.fullmatch(r"\{(\w+)\}", value)
    if m:
        if m.group(1) not in ctx:
            raise KeyError(f"profile uses {{{m.group(1)}}} but no such value exists")
        return ctx[m.group(1)]
    return re.sub(r"\{(\w+)\}", lambda k: str(ctx.get(k.group(1), k.group(0))), value)


def run_graph(profile, graph_rel, set_map, ctx, run_tag):
    """Fill a graph from `set_map`, run it, and return the audio files it saved."""
    path = profiles.graph_path({**profile, "graph": graph_rel})
    g = json.load(open(path, encoding="utf-8-sig"))
    missing = []
    for target, value in set_map.items():
        optional = target.startswith("?")
        node, _, key = target.lstrip("?").partition(".")
        if node not in g:
            if not optional:
                missing.append(f"{target} (node {node} not in the graph)")
            continue
        filled = _fill(value, ctx)
        if filled is not None:  # null keeps the graph's own value
            g[node]["inputs"][key] = filled
    if missing:
        raise ValueError(f"profile '{profile['id']}' sets inputs its graph does not have: {', '.join(missing)}")
    out_node = profile.get("output_node", "")
    if not g.get(out_node, {}).get("class_type", "").startswith("SaveAudio"):
        out_node = ""  # e.g. a variant graph whose save node has another id
    for nid, node in g.items():  # every SaveAudio writes under this run's tag
        if node["class_type"].startswith("SaveAudio") and (not out_node or nid == out_node):
            node["inputs"]["filename_prefix"] = f"{OUT_SUBFOLDER}/{run_tag}"

    group = profile.get("vram_group")
    if group != _vram["group"] and _vram["group"] is not None:
        comfy.free_vram()
    try:
        seconds, steps = comfy.run_graph(g)
    except comfy.ComfyError as e:
        if "OutOfMemory" not in str(e) and "out of memory" not in str(e).lower():
            raise
        log("out of GPU memory - freeing VRAM and retrying once ...")
        comfy.free_vram()
        seconds, steps = comfy.run_graph(g)
    _vram["group"] = group
    files = comfy.outputs_of(f"{OUT_SUBFOLDER}/{run_tag}", ".flac")
    if not files:
        raise RuntimeError(f"the graph ran but saved no audio under {OUT_SUBFOLDER}/{run_tag}")
    return files, seconds, steps


def build_prompt(profile, prompt, ctx, style="", style_text=""):
    parts = [t.strip().rstrip(".") for t in (style_text, profile.get("style"), style) if t and t.strip()]
    text = profile.get("prompt_template", "{prompt}")
    text = text.replace("{prompt}", prompt.strip().rstrip("."))
    text = text.replace("{style}", (", " + ", ".join(parts)) if parts else "")
    text = _fill(text, ctx)
    return re.sub(r"\s{2,}", " ", text).strip()


def _settings_key(p, prompt, extra):
    blob = json.dumps({"profile": p["id"], "params": p["params"], "prompt": prompt, "extra": extra}, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def _upload(path, name):
    os.makedirs(comfy.input_dir(), exist_ok=True)
    shutil.copyfile(path, os.path.join(comfy.input_dir(), name))
    return name


# ----------------------------------------------------------------------------- voices

def voice_info(voice, project_dir=None):
    vid = safe_name(voice)
    base = os.path.join(voices_dir(project_dir), vid)
    meta = base + ".json"
    if os.path.isfile(base + ".wav") and os.path.isfile(meta):
        return {"voice": vid, "reference": base + ".wav", **json.load(open(meta, encoding="utf-8"))}
    return None


def list_voices(project_dir=None):
    d = voices_dir(project_dir)
    out = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith(".json"):
                info = voice_info(f[:-5], project_dir)
                if info:
                    out.append(info)
    return out


def design_voice(voice, description, project_dir=None, seed=None, language="Auto", force=False):
    """Create a character voice from a description; saves voices/<voice>.wav + .json."""
    vid = safe_name(voice)
    existing = voice_info(vid, project_dir)
    if existing and not force:
        return {"status": "ok", "cached": True, **existing}
    if not description:
        raise ValueError(f"voice '{vid}' does not exist yet: give voice_description (who is speaking and how they sound)")
    p = profiles.resolve("voice", project_dir)
    seed = random.randint(0, 2**31 - 1) if seed is None else int(seed)
    ctx = {**p["params"], "text": REFERENCE_LINE, "instruct": description.strip(), "language": language, "seed": seed}
    comfy.ensure_server()
    files, seconds, _ = run_graph(p, p["graph"], p["set"], ctx, f"voice_{vid}_{uuid.uuid4().hex[:6]}")
    d = voices_dir(project_dir)
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, vid + ".wav")
    raw, final, _ = audio.process(files[-1], dst, {"trim": True, "trim_db": -45, "channels": "mono", "loudness": -20.0,
                                                   "peak_db": -1.0, "format": "wav"}, "voice")
    meta = {"description": description.strip(), "reference_text": REFERENCE_LINE, "seed": seed, "language": language,
            "created": time.strftime("%Y-%m-%d %H:%M")}
    json.dump(meta, open(os.path.join(d, vid + ".json"), "w", encoding="utf-8"), indent=2)
    problems = audio.problems_of(raw, final, "voice")
    return {"status": "ok" if not problems else "failed_check", "voice": vid, "reference": dst, "seconds": final["seconds"],
            "problems": problems, "generation_s": seconds, **meta}


# ----------------------------------------------------------------------------- sounds

def generate_sound(profile_id, name, prompt=None, project_dir=None, out_dir=None, seed=None, style="", params=None,
                   force=False, preset="standard", style_preset=None, lyrics=None, voice=None, voice_description=None):
    """Text -> game-ready audio file. Returns a manifest dict (also written as <name>.json)."""
    name = safe_name(name)
    p = profiles.resolve(profile_id, project_dir, params, preset=preset, style=style_preset)
    kind = p.get("kind")
    if kind not in ("sfx", "ambience", "music", "voice"):
        raise ValueError(f"'{profile_id}' is not a sound profile")
    if not prompt:
        raise ValueError("give a prompt (for a voice line: the words to speak)")
    out = out_dir_for(project_dir, out_dir)
    os.makedirs(out, exist_ok=True)
    fmt = p["params"].get("format", "wav")
    dst = os.path.join(out, f"{name}.{fmt}")
    manifest_path = os.path.join(out, f"{name}.json")

    seed_given = seed is not None
    seed = random.randint(0, 2**31 - 1) if seed is None else int(seed)
    ctx = {**p["params"], "seed": seed}
    graph, set_map = p["graph"], dict(p.get("set", {}))
    voice_used = None
    if kind == "voice":
        ctx.update(text=prompt.strip(), instruct=(p["params"].get("emotion") or "").strip(), lyrics="")
        if voice:
            voice_used = voice_info(voice, project_dir) or design_voice(voice, voice_description, project_dir,
                                                                       language=p["params"].get("language", "Auto"))
            if voice_used.get("status") == "failed_check":
                return {"name": name, "status": "failed_check", "problems": ["the new voice's reference line failed its check: "
                                                                             + "; ".join(voice_used["problems"])],
                        "voice": voice_used}
            clone = p["variants"]["clone"]
            graph, set_map = clone["graph"], dict(clone["set"])
            ctx.update(ref_file=_upload(voice_used["reference"], f"soundforge_voice_{voice_used['voice']}.wav"),
                       ref_text=voice_used["reference_text"])
        else:
            desc = (voice_description or p["params"].get("voice_description") or "").strip()
            if not desc:
                raise ValueError("a voice line needs `voice` (a saved character) or `voice_description` (who speaks and how)")
            ctx["instruct"] = ". ".join(t for t in (desc.rstrip("."), ctx["instruct"]) if t)
        text_for_score = None
    else:
        ctx["lyrics"] = lyrics if lyrics is not None else p["params"].get("lyrics", "[Instrumental]")
        ctx["length"] = max(1, int(round(float(p["params"].get("duration", 5)))))
        ctx["prompt"] = build_prompt(p, prompt, ctx, style, p.get("style_text", ""))
        ctx["duration"] = max(1.0, float(p["params"].get("duration", 5)))
        text_for_score = prompt.strip()
    ctx["negative"] = p["params"].get("negative", "")

    # Same name + same settings returns the existing file; any change (or force) makes a new one.
    key = _settings_key(p, prompt, {"lyrics": ctx.get("lyrics"), "voice": voice_used and voice_used["voice"],
                                    "voice_description": voice_description, "style": style, "seed": seed if seed_given else None})
    if os.path.isfile(dst) and os.path.isfile(manifest_path) and not force:
        old = json.load(open(manifest_path, encoding="utf-8"))
        if old.get("settings_key") == key:
            return {**old, "cached": True}

    comfy.ensure_server()
    n = max(1, int(p["params"].get("candidates", 1)))
    run_tag = f"{name}_{uuid.uuid4().hex[:6]}"
    t0 = time.time()
    raws, gen_s, node_steps = [], 0.0, []
    if p.get("batch", False):  # one sampler run makes all candidates
        ctx["candidates"] = n
        raws, gen_s, node_steps = run_graph(p, graph, set_map, ctx, run_tag)
        seeds = [seed] * len(raws)
    else:  # one run per candidate, each with its own seed
        seeds = []
        for i in range(n):
            files, s, node_steps = run_graph(p, graph, set_map, {**ctx, "seed": seed + i}, f"{run_tag}_{i}")
            raws.append(files[-1])
            seeds.append(seed + i)
            gen_s += s

    work = os.path.join(out, ".soundforge", name)
    os.makedirs(work, exist_ok=True)
    cands = []
    for i, raw in enumerate(raws):
        cand_path = os.path.join(work, f"candidate_{i}.{fmt}")
        raw_stats, final, steps = audio.process(raw, cand_path, p["params"], kind)
        cands.append({"index": i, "seed": seeds[i], "file": cand_path, "raw_file": raw,
                      "problems": audio.problems_of(raw_stats, final, kind), "stats": final, "steps": steps})

    if text_for_score and len(cands) > 1 and p["params"].get("rank_by_clap", True) and score.available():
        try:
            for c, s in zip(cands, score.clap_scores([c["file"] for c in cands], text_for_score)):
                c["clap"] = s
        except Exception as e:
            log(f"CLAP scoring failed ({e}); keeping the first clean candidate")
    best = sorted(cands, key=lambda c: (len(c["problems"]), -(c.get("clap") or 0), c["index"]))[0]
    shutil.copyfile(best["file"], dst)
    if not p["params"].get("keep_candidates", True):
        shutil.rmtree(work, ignore_errors=True)

    result = {
        "name": name, "status": "ok" if not best["problems"] else "failed_check", "file": dst,
        "profile": p["id"], "preset": p["preset"], "kind": kind, "style_preset": p.get("style_preset"),
        "prompt": prompt, "model_prompt": ctx.get("prompt") if kind != "voice" else ctx.get("instruct"),
        "lyrics": ctx.get("lyrics") if kind == "music" else None,
        "voice": voice_used and {k: voice_used.get(k) for k in ("voice", "description", "reference")},
        "seed": best["seed"], "problems": best["problems"], "audio": best["stats"], "processing": best["steps"],
        "candidates": [{k: c.get(k) for k in ("index", "seed", "clap", "problems", "file")} for c in cands],
        "chosen": best["index"], "chosen_by": "CLAP prompt match" if best.get("clap") is not None else "first clean candidate",
        "timings": {"generation_s": round(gen_s, 1), "total_s": round(time.time() - t0, 1)},
        "slowest_nodes": node_steps[:3], "settings": p["params"], "limited_by_vram": p.get("limited_by_vram") or None,
        "style_ignored": p.get("style_ignored") or None, "preset_note": p.get("preset_note"), "settings_key": key,
    }
    result = {k: v for k, v in result.items() if v is not None}
    json.dump(result, open(manifest_path, "w", encoding="utf-8"), indent=2)
    return result


def generate_batch(jobs, project_dir=None, out_dir=None, style="", force=False):
    """jobs: [{"name", "prompt", "profile"?, "preset"?, "params"?, "voice"?, ...}]. Grouped by model."""
    order = []
    for i, job in enumerate(jobs):
        pid = job.get("profile", "sfx")
        group = profiles.resolve(pid, project_dir).get("vram_group", "")
        order.append((group, i, job))
    results = [None] * len(jobs)
    for _g, i, job in sorted(order, key=lambda t: (t[0], t[1])):
        try:
            results[i] = generate_sound(job.get("profile", "sfx"), job["name"], job.get("prompt"), project_dir, out_dir,
                                        job.get("seed"), job.get("style", style), job.get("params"), job.get("force", force),
                                        job.get("preset", "standard"), job.get("style_preset"), job.get("lyrics"),
                                        job.get("voice"), job.get("voice_description"))
        except Exception as e:
            results[i] = {"name": job.get("name"), "status": "error", "error": f"{type(e).__name__}: {e}"}
    return results


def check_file(path, kind="sfx"):
    data, rate = audio.load(path)
    stats = audio.analyse(data, rate)
    return {"status": "ok", "audio": stats, "problems": audio.problems_of(stats, stats, kind)}
