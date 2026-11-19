"""Turning raw model output into a game-ready file, and checking it.

Steps, in order (each is a profile parameter, so a profile or a call can switch it off):
  trim      cut leading and trailing silence (threshold `trim_db` below the peak)
  length    cut to `max_seconds`
  loop      make the end flow into the start: the last `loop_crossfade` seconds are
            blended over the first ones with an equal-power crossfade, so the file
            repeats without a click. With `bpm` set, the loop is cut to whole bars first.
  fades     short fade in / out (skipped for loops, which must not dip)
  channels  mono (positional 3D sounds) or stereo (ambience, music, UI)
  loudness  integrated loudness (ITU-R BS.1770) to `loudness` LUFS, then the peak is
            kept at or below `peak_db` dBFS by lowering the gain - never by clipping.
            Clips under 0.4 s are too short to measure and are peak-normalised instead.
  export    wav (16-bit PCM) or ogg (Vorbis), at the model's rate or `sample_rate`
"""
import math
import os

import numpy as np
import soundfile as sf


def load(path):
    data, rate = sf.read(path, always_2d=True, dtype="float32")
    return data, rate


def db(x):
    return 20 * math.log10(max(float(x), 1e-12))


def _frames_rms(data, rate, win_s=0.01):
    n = max(1, int(rate * win_s))
    mono = np.abs(data).max(axis=1)
    pad = (-len(mono)) % n
    mono = np.pad(mono, (0, pad))
    return mono.reshape(-1, n).max(axis=1), n


def trim(data, rate, threshold_db=-50.0, keep_s=0.01):
    """Cut silence at both ends; `threshold_db` is relative to the clip's own peak."""
    peak = float(np.abs(data).max()) if data.size else 0.0
    if peak <= 0:
        return data
    env, n = _frames_rms(data, rate)
    loud = np.where(env >= peak * 10 ** (threshold_db / 20))[0]
    if not len(loud):
        return data
    keep = int(keep_s * rate)
    start = max(0, loud[0] * n - keep)
    end = min(len(data), (loud[-1] + 1) * n + keep)
    return data[start:end]


def fades(data, rate, fade_in_s=0.005, fade_out_s=0.05):
    out = data.copy()
    i = min(len(out) // 4, int(fade_in_s * rate))
    o = min(len(out) // 4, int(fade_out_s * rate))
    if i > 0:
        out[:i] *= np.linspace(0, 1, i, dtype=np.float32)[:, None]
    if o > 0:
        out[-o:] *= np.linspace(1, 0, o, dtype=np.float32)[:, None]
    return out


def make_loop(data, rate, crossfade_s=1.0, bpm=None, beats_per_bar=4):
    """Equal-power crossfade of the tail into the head; the result is `crossfade_s` shorter."""
    if bpm:
        bar = 60.0 / bpm * beats_per_bar
        bars = int((len(data) / rate - crossfade_s) // bar)
        if bars >= 1:
            data = data[:int(round((bars * bar + crossfade_s) * rate))]
    x = int(crossfade_s * rate)
    x = min(x, len(data) // 3)
    if x < 2:
        return data
    t = np.linspace(0, math.pi / 2, x, dtype=np.float32)[:, None]
    head, tail = data[:x], data[-x:]
    blended = tail * np.cos(t) + head * np.sin(t)
    return np.concatenate([blended, data[x:-x]], axis=0)


def to_channels(data, channels):
    if channels == "mono" and data.shape[1] > 1:
        return data.mean(axis=1, keepdims=True)
    if channels == "stereo" and data.shape[1] == 1:
        return np.repeat(data, 2, axis=1)
    return data


def loudness_lufs(data, rate):
    if len(data) < int(0.4 * rate):
        return None
    import pyloudnorm as pyln
    value = pyln.Meter(rate).integrated_loudness(data)
    return None if not math.isfinite(value) else round(float(value), 1)


def normalise(data, rate, target_lufs=-18.0, peak_db=-1.0):
    """Gain only: reach the loudness target unless that would push the peak over `peak_db`."""
    peak = float(np.abs(data).max()) if data.size else 0.0
    if peak <= 0:
        return data, None
    measured = loudness_lufs(data, rate)
    gain_db = (target_lufs - measured) if measured is not None else (peak_db - db(peak))
    gain_db = min(gain_db, peak_db - db(peak))  # the peak limit wins
    return (data * 10 ** (gain_db / 20)).astype(np.float32), round(gain_db, 1)


def resample(data, rate, new_rate):
    if not new_rate or new_rate == rate:
        return data, rate
    from scipy.signal import resample_poly
    g = math.gcd(int(rate), int(new_rate))
    return resample_poly(data, new_rate // g, rate // g, axis=0).astype(np.float32), new_rate


def analyse(data, rate):
    peak = float(np.abs(data).max()) if data.size else 0.0
    rms = float(np.sqrt(np.mean(data ** 2))) if data.size else 0.0
    env, _n = _frames_rms(data, rate)
    quiet = float(np.mean(env < max(peak, 1e-9) * 10 ** (-40 / 20))) if len(env) else 1.0
    return {
        "seconds": round(len(data) / rate, 3),
        "sample_rate": rate,
        "channels": int(data.shape[1]),
        "peak_db": round(db(peak), 1),
        "rms_db": round(db(rms), 1),
        "loudness_lufs": loudness_lufs(data, rate),
        "clipped_ratio": round(float(np.mean(np.abs(data) >= 0.999)), 5),
        "quiet_ratio": round(quiet, 3),
        "dc_offset": round(float(np.abs(data.mean(axis=0)).max()), 4) if data.size else 0.0,
    }


def problems_of(raw_stats, final_stats, kind):
    """Things that make a clip unusable. `raw_stats` is the model output before processing."""
    out = []
    if raw_stats["peak_db"] < -45:
        out.append("silent: the model produced (almost) nothing")
    if raw_stats["clipped_ratio"] > 0.002:
        out.append(f"distorted: {raw_stats['clipped_ratio'] * 100:.1f}% of samples clip")
    if kind in ("sfx", "voice") and final_stats["seconds"] < 0.05:
        out.append("too short after trimming silence")
    if kind == "ambience" and raw_stats["quiet_ratio"] > 0.5:
        out.append(f"gappy: {raw_stats['quiet_ratio'] * 100:.0f}% of the ambience is near-silent")
    if kind == "music" and raw_stats["quiet_ratio"] > 0.35:
        out.append(f"gappy: {raw_stats['quiet_ratio'] * 100:.0f}% of the music is near-silent")
    if final_stats["dc_offset"] > 0.05:
        out.append("DC offset (the waveform is off-centre)")
    return out


def process(src, dst, p, kind):
    """Apply the profile's steps to one raw file. Returns (raw stats, final stats, steps applied)."""
    data, rate = load(src)
    raw = analyse(data, rate)
    steps = []
    if p.get("trim", False):
        data = trim(data, rate, p.get("trim_db", -50.0))
        steps.append("trim")
    if p.get("max_seconds"):
        data = data[: int(p["max_seconds"] * rate)]
    if p.get("loop", False):
        data = make_loop(data, rate, p.get("loop_crossfade", 1.0), p.get("bpm") if p.get("loop_bars", True) else None)
        steps.append("loop")
    elif p.get("fade_out", 0) or p.get("fade_in", 0):
        data = fades(data, rate, p.get("fade_in", 0.0), p.get("fade_out", 0.0))
        steps.append("fades")
    data = to_channels(data, p.get("channels", "keep"))
    data, rate = resample(data, rate, p.get("sample_rate"))
    gain = None
    if p.get("loudness") is not None:
        data, gain = normalise(data, rate, p["loudness"], p.get("peak_db", -1.0))
        steps.append("loudness")
    data = np.clip(data, -1.0, 1.0)
    fmt = p.get("format", "wav").lower()
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    if fmt == "ogg":
        sf.write(dst, data, rate, format="OGG", subtype="VORBIS")
    else:
        sf.write(dst, data, rate, subtype="PCM_16")
    final = analyse(data, rate)
    final["gain_db"] = gain
    return raw, final, steps
