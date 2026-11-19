"""Ranking candidates: how well each clip matches its prompt (LAION CLAP).

Generating several candidates and keeping the best is the cheapest quality lever for
these models (TangoFlux paper: CLAP-ranked best-of-N keeps improving up to about
N = 5-10). CLAP runs on the CPU so it never competes with ComfyUI for VRAM; scoring
a handful of short clips takes a few seconds. The model (about 0.8 GB) is downloaded
by `forge.py setup` or on first use.
"""
import os

import numpy as np

from .config import FORGE_ROOT, log

CLAP_MODEL = "laion/larger_clap_general"
_state = {}


def available():
    try:
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


def _load():
    if "model" not in _state:
        from transformers import ClapModel, ClapProcessor
        log(f"loading {CLAP_MODEL} for scoring ...")
        cache = os.path.join(FORGE_ROOT, "models", "hf_cache")
        _state["processor"] = ClapProcessor.from_pretrained(CLAP_MODEL, cache_dir=cache)
        _state["model"] = ClapModel.from_pretrained(CLAP_MODEL, cache_dir=cache).eval()
    return _state["processor"], _state["model"]


def clap_scores(paths, text):
    """Cosine similarity between `text` and each audio file (higher = closer to the prompt)."""
    import torch
    from scipy.signal import resample_poly

    from .audio import load

    processor, model = _load()
    rate_needed = processor.feature_extractor.sampling_rate  # 48 kHz
    clips = []
    for path in paths:
        data, rate = load(path)
        mono = data.mean(axis=1)
        if rate != rate_needed:
            g = np.gcd(int(rate), int(rate_needed))
            mono = resample_poly(mono, rate_needed // g, rate // g)
        clips.append(mono[: rate_needed * 10].astype(np.float32))  # CLAP looks at 10 s
    with torch.no_grad():
        t = processor(text=[text], return_tensors="pt", padding=True)
        a = processor(audio=clips, sampling_rate=rate_needed, return_tensors="pt", padding=True)
        te = model.get_text_features(**t)
        ae = model.get_audio_features(**a)
        te = te.pooler_output if hasattr(te, "pooler_output") else te
        ae = ae.pooler_output if hasattr(ae, "pooler_output") else ae
        te = te / te.norm(dim=-1, keepdim=True)
        ae = ae / ae.norm(dim=-1, keepdim=True)
        return [round(float(s), 4) for s in (ae @ te.T).squeeze(-1)]
