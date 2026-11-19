r"""Smoke test: one job per profile (and the voice-consistency path), with timings and peak VRAM.

    python tests/smoke_test.py                 every job at the standard preset
    python tests/smoke_test.py --preset max    every job at max
    python tests/smoke_test.py --only voice    jobs whose name contains "voice"

Output: tests/results/<run>/ with the sounds, their manifests and results.json.
Peak VRAM is the whole GPU's (nvidia-smi), so close other GPU programs first.
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from soundforge import comfy, pipeline  # noqa: E402

JOBS = [
    ("sfx_door", "sfx", "Heavy wooden door slamming shut in a stone hall, deep thud with a short echo", {"duration": 3}, {}),
    ("sfx_coin", "sfx", "Gold coins dropping into a leather pouch, bright metallic jingle, close", {"duration": 2}, {}),
    ("sfx_spell", "sfx", "Fire spell cast, whooshing ignition followed by a roaring burst of flame", {"duration": 3}, {}),
    ("ambience_cave", "ambience", "Damp cave interior, slow water drips echoing, low wind rumble, distant trickling stream", {}, {}),
    ("stinger_levelup", "stinger", "Level up chime, bright ascending harp and bell arpeggio, rewarding fantasy RPG", {}, {}),
    ("music_explore", "music_loop", "Calm fantasy exploration music, acoustic guitar, soft strings, flute melody, warm and adventurous",
     {"bpm": 90, "keyscale": "D major", "duration": 60}, {}),
    ("voice_keeper_1", "voice", "Who goes there? The graveyard is closed after dark.", {"emotion": "suspicious, gruff"},
     {"voice": "smoke_grave_keeper", "voice_description": "An old man with a deep gravelly voice, slow and weary, slight Scottish accent"}),
    ("voice_keeper_2", "voice", "Fine, fine. Take the lantern, and do not wake the dead.", {"emotion": "tired, reluctant"},
     {"voice": "smoke_grave_keeper"}),
]


class VramPeak:
    def __init__(self):
        self.peak, self._stop = 0, False

    def _run(self):
        while not self._stop:
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=5).stdout
                self.peak = max(self.peak, max(int(x) for x in out.split()))
            except Exception:
                pass
            time.sleep(0.5)

    def __enter__(self):
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def __exit__(self, *a):
        self._stop = True


def run(only=None, preset="standard"):
    stamp = time.strftime("%Y%m%d_%H%M")
    out = os.path.join(HERE, "results", stamp)
    rows = []
    comfy.ensure_server()
    for name, profile, prompt, params, extra in JOBS:
        if only and not any(o in name for o in only.split(",")):
            continue
        t0 = time.time()
        with VramPeak() as vp:
            try:
                r = pipeline.generate_sound(profile, name, prompt, out_dir=out, seed=1234, params=params, preset=preset,
                                            force=True, project_dir=None, **extra)
            except Exception as e:
                r = {"status": "error", "error": f"{type(e).__name__}: {e}"}
        row = {"job": name, "profile": profile, "status": r.get("status"), "error": r.get("error"),
               "wall_s": round(time.time() - t0, 1), "peak_vram_gb": round(vp.peak / 1024, 1),
               "seconds": (r.get("audio") or {}).get("seconds"), "lufs": (r.get("audio") or {}).get("loudness_lufs"),
               "peak_db": (r.get("audio") or {}).get("peak_db"), "problems": r.get("problems"),
               "candidates": [(c.get("clap"), c.get("problems")) for c in r.get("candidates", [])],
               "chosen": r.get("chosen"), "file": r.get("file"), "timings": r.get("timings")}
        rows.append(row)
        print(json.dumps(row), flush=True)
        os.makedirs(out, exist_ok=True)
        json.dump(rows, open(os.path.join(out, "results.json"), "w", encoding="utf-8"), indent=2)
    print(json.dumps({"status": "ok", "results": os.path.join(out, "results.json")}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--preset", default="standard", choices=["fast", "standard", "max"])
    a = ap.parse_args()
    run(a.only, a.preset)
