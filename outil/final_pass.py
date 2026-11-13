"""After the meeting: a slower, better pass over the full recording.

The live pass labels voices by stream only (microphone or system output). This pass re-cuts
both streams with wider windows, transcribes them again, and splits the system output into its
speakers with pyannote, so two remote participants get separate labels.

Usage:
  python final_pass.py <meeting folder> [--remote-speakers 2] [--threads 16] [--no-diarization]
Writes final/transcript.final.md, final/diarization.tsv, final/windows.json and final/summary.json.
"""
import argparse
import glob
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textclean import clean  # noqa: E402

SR = 16000
FRAME = 320
REPO = "CohereLabs/cohere-transcribe-arabic-07-2026"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def hms(s):
    s = max(0, int(s))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def load_stream(folder, key):
    parts = sorted(glob.glob(os.path.join(folder, "audio", f"{key}-*.wav")))
    if not parts:
        return np.zeros(0, dtype=np.float32)
    chunks = []
    for p in parts:
        try:
            a, sr = sf.read(p, dtype="float32", always_2d=True)
        except RuntimeError:  # a part left open by a crash: read the raw PCM after the 44-byte header
            raw = np.fromfile(p, dtype="<i2", offset=44)
            a, sr = (raw.astype(np.float32) / 32768.0)[:, None], 48000
        x = a.mean(axis=1)
        chunks.append(resample_poly(x, SR, sr).astype(np.float32) if sr != SR else x)
    return np.concatenate(chunks)


def windows_for(audio, max_s=28.0):
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    spans = get_speech_timestamps(audio, VadOptions(threshold=0.5, min_silence_duration_ms=500, speech_pad_ms=300))
    out = []
    for s in spans:
        a, b = s["start"] / SR, s["end"] / SR
        while b - a > max_s:
            out.append([a, a + max_s])
            a += max_s
        if out and b - out[-1][0] <= max_s and a - out[-1][1] < 2.0:
            out[-1][1] = b
        else:
            out.append([a, b])
    return out


def windows_from_turns(turns, total_s, max_s=28.0, min_s=0.6, join_gap=1.0):
    """Windows along the speaker turns: consecutive turns of one speaker are joined across
    short pauses, long turns are cut at max_s, and fragments under min_s are dropped."""
    out = []
    for s, e, spk in sorted(turns):
        s, e = max(0.0, s), min(total_s, e)
        if out and out[-1][2] == spk and s - out[-1][1] < join_gap and e - out[-1][0] <= max_s:
            out[-1][1] = e
            continue
        while e - s > max_s:
            out.append([s, s + max_s, spk])
            s += max_s
        out.append([s, e, spk])
    return [w for w in out if w[1] - w[0] >= min_s]


def gate(mic, remote, mic_off, rem_off, thr):
    """Zero the microphone where the system output was speaking (echo from loudspeakers)."""
    n = len(remote) // FRAME
    if not n or not len(mic):
        return mic
    act = np.sqrt((remote[: n * FRAME].reshape(n, FRAME) ** 2).mean(axis=1)) > thr
    c = np.concatenate([[0], np.cumsum(act.astype(np.int32))])
    k = (len(mic) + FRAME - 1) // FRAME
    f = np.round((mic_off - rem_off) * SR / FRAME).astype(int) + np.arange(k)
    lo, hi = np.clip(f - 25, 0, n), np.clip(f + 16, 0, n)
    m = (c[hi] - c[lo]) > 0
    y = mic.copy()
    y[np.repeat(m, FRAME)[: len(y)]] = 0.0
    return y


class Cohere:
    def __init__(self, threads):
        import torch
        from transformers import AutoProcessor, CohereAsrForConditionalGeneration
        torch.set_num_threads(threads)
        self.torch = torch
        self.proc = AutoProcessor.from_pretrained(REPO)
        try:
            self.model = CohereAsrForConditionalGeneration.from_pretrained(REPO, dtype=torch.bfloat16)
        except TypeError:
            self.model = CohereAsrForConditionalGeneration.from_pretrained(REPO, torch_dtype=torch.bfloat16)
        self.model.eval()

    def __call__(self, piece, max_tokens=256):
        # REUNION_LANG : langue de la réunion ("fr" pour un entretien en français) ; "ar" par défaut.
        inputs = self.proc(piece, sampling_rate=SR, return_tensors="pt",
                           language=os.environ.get("REUNION_LANG", "ar"))
        inputs.to(self.model.device, dtype=self.model.dtype)
        with self.torch.inference_mode():
            ids = self.model.generate(**inputs, max_new_tokens=max_tokens)
        t = self.proc.decode(ids, skip_special_tokens=True)
        return (t[0] if isinstance(t, list) else t).strip(), int(ids.shape[-1])

    def robust(self, piece):
        text, ntok = self(piece)
        _, cut = clean(text)
        if (cut or ntok >= 256) and len(piece) > 4 * SR:   # a loop: transcribe the two halves
            h = len(piece) // 2
            text = (self(piece[:h], 160)[0] + " " + self(piece[h:], 160)[0]).strip()
        return clean(text)[0]


def diarize(remote, speakers, out_tsv):
    import torch
    from pyannote.audio import Pipeline
    pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-community-1")
    kw = {"num_speakers": speakers} if speakers else {}
    res = pipe({"waveform": torch.from_numpy(remote[None, :]), "sample_rate": SR}, **kw)
    # community-1 also returns a version without overlaps: one speaker at a time, so no text twice
    diar = getattr(res, "exclusive_speaker_diarization", None) or getattr(res, "speaker_diarization", res)
    turns = [(t.start, t.end, spk) for t, _, spk in diar.itertracks(yield_label=True)]
    with open(out_tsv, "w", encoding="utf-8") as f:
        for a, b, s in turns:
            f.write(f"{a:.2f}\t{b:.2f}\t{s}\n")
    return turns


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("folder")
    p.add_argument("--remote-speakers", type=int, default=0, help="number of remote speakers, if known")
    p.add_argument("--threads", type=int, default=16)
    p.add_argument("--gate-threshold", type=float, default=0.004)
    p.add_argument("--no-echo-gate", dest="echo_gate", action="store_false", default=None,
                   help="default: as in the live run (live/labels.json), else on")
    p.add_argument("--no-diarization", dest="diarize", action="store_false")
    a = p.parse_args()
    folder = os.path.abspath(a.folder)
    os.makedirs(os.path.join(folder, "final"), exist_ok=True)
    meta = {}
    for name in ("summary.json", "status.json"):
        path = os.path.join(folder, "live", name)
        if os.path.exists(path):
            meta = json.load(open(path, encoding="utf-8"))
            break
    me = a_label(folder, "me") or "Moi"
    if a.echo_gate is None:
        live_gate = a_label(folder, "echo_gate")
        a.echo_gate = True if live_gate is None else bool(live_gate)
    mic_off = meta.get("mic_offset_s") or 0.0
    rem_off = meta.get("remote_offset_s") or 0.0
    t0 = time.time()
    mic, rem = load_stream(folder, "mic"), load_stream(folder, "remote")
    log(f"audio : micro {len(mic) / SR / 60:.1f} min, sortie {len(rem) / SR / 60:.1f} min")
    if a.echo_gate:
        mic = gate(mic, rem, mic_off, rem_off, a.gate_threshold)

    # Diarize the system output first, so its windows follow the speaker turns: one voice per window.
    turns = []
    if a.diarize and len(rem) > SR:
        log("séparation des voix (pyannote)…")
        turns = diarize(rem, a.remote_speakers or None, os.path.join(folder, "final", "diarization.tsv"))
    talk = defaultdict(float)
    for s, e, spk in turns:
        talk[spk] += e - s
    names = {spk: f"Voix {k + 1}" for k, (spk, _) in enumerate(sorted(talk.items(), key=lambda x: -x[1]))}
    remote_label = a_label(folder, "remote") or "Participants"

    asr = Cohere(a.threads)
    lines, wins = [], {}
    for key, audio, off in (("mic", mic, mic_off), ("remote", rem, rem_off)):
        if key == "remote" and turns:
            w = windows_from_turns(turns, len(audio) / SR)
        else:
            w = [[s, e, None] for s, e in windows_for(audio)] if len(audio) > SR else []
        wins[key] = w
        log(f"{key} : {len(w)} fenêtres")
        for i, (s, e, spk) in enumerate(w):
            text = asr.robust(audio[int(s * SR):int(e * SR)])
            if text:
                lab = me if key == "mic" else (names.get(spk) or remote_label)
                lines.append([off + s, off + e, lab, text])
            if i % 20 == 0:
                log(f"  {key} {i}/{len(w)}")

    lines.sort(key=lambda x: x[0])
    title = meta.get("title") or os.path.basename(folder)
    with open(os.path.join(folder, "final", "transcript.final.md"), "w", encoding="utf-8") as f:
        f.write(f"# Transcription finale : {title}\n\n")
        f.write(f"Voix : {me} = micro ; " + (", ".join(f"{v} = {round(talk[k] / 60, 1)} min" for k, v in names.items()) or remote_label)
                + " (sortie audio, séparée par pyannote ; à identifier). Texte d'un modèle local : à vérifier avant de citer.\n\n")
        for s, e, lab, text in lines:
            f.write(f"[{hms(s)}] **{lab}** : {text}\n")
    json.dump(wins, open(os.path.join(folder, "final", "windows.json"), "w"))
    summ = {"minutes_mic": round(len(mic) / SR / 60, 1), "minutes_remote": round(len(rem) / SR / 60, 1),
            "lines": len(lines), "remote_voices": {v: round(talk[k] / 60, 1) for k, v in names.items()},
            "seconds": round(time.time() - t0)}
    json.dump(summ, open(os.path.join(folder, "final", "summary.json"), "w", encoding="utf-8"), indent=1)
    log("terminé :", json.dumps(summ, ensure_ascii=False))


def a_label(folder, which):
    """Labels given to the live run, read back from its transcript header."""
    path = os.path.join(folder, "live", "labels.json")
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8")).get(which)
    return None


if __name__ == "__main__":
    main()
