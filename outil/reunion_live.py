"""Record a meeting locally and transcribe it while it happens.

Two separate streams: your microphone (you) and the system output through WASAPI loopback
(the other participants of a Google Meet, Zoom or Teams call). Each stream is cut into speech
windows by a VAD and transcribed by Cohere Transcribe Arabic, which handles Tunisian darja
mixed with French and English. Nothing leaves the machine.

Usage:
  python reunion_live.py --out <meeting folder> [--me "<your name>"] [--remote "<the others>"] [--title ...]
  python reunion_live.py --list-devices
  python reunion_live.py --out <folder> --simulate <audio file> [--sim-start 600] [--sim-dur 180]

Stop: create a file named STOP in the meeting folder, or press Ctrl+C.
Output in <out>: audio/*.wav (48 kHz, 5-minute parts), live/transcript.md, live/live.html
(opens in a browser, refreshes every 5 s), live/notes.md (written by the note taker),
live/events.jsonl, live/status.json and, at the end, live/summary.json.
"""
import argparse
import html
import json
import os
import queue
import re
import sys
import threading
import time
from datetime import datetime

import numpy as np

# soundcard 0.4.5 calls numpy.fromstring in binary mode, which numpy 2 removed.
_np_fromstring = np.fromstring


def _fromstring(s, dtype=float, count=-1, sep=''):
    if sep == '':
        return np.frombuffer(bytes(s), dtype=dtype, count=count).copy()
    return _np_fromstring(s, dtype=dtype, count=count, sep=sep)


np.fromstring = _fromstring

import soundfile as sf  # noqa: E402
from scipy.signal import resample_poly  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textclean import clean  # noqa: E402

SR_DEV, SR = 48000, 16000
BLOCK = 4800                      # 0.1 s at 48 kHz
FRAME = 320                       # 20 ms at 16 kHz, for the echo gate
MAX_WIN, MIN_WIN = 20.0, 0.6      # seconds per transcription window (8-20 s loops less, per the 21/10 research)
CLOSE_SIL = 0.7                   # silence that closes a speech span
PART_SECONDS = 300                # rotate the archive WAV every 5 minutes
REPO = "CohereLabs/cohere-transcribe-arabic-07-2026"

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def hms(s):
    s = max(0, int(s))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


class Channel:
    """One audio stream: an archive writer, plus a 16 kHz buffer for the VAD, on a wall clock."""

    def __init__(self, key, label, folder):
        self.key, self.label, self.folder = key, label, folder
        self.lock = threading.Lock()
        self.buf = np.zeros(0, dtype=np.float32)    # pending 16 kHz audio
        self.buf_start = 0                          # sample index (16 kHz) of buf[0]
        self.total = 0                              # 16 kHz samples received so far
        self.origin = None                          # wall time of sample 0
        self.rms_recent = 0.0
        self.writer, self.part, self.part_samples = None, 0, 0
        self.active = np.zeros(0, dtype=bool)       # remote only: speaking, per 20 ms frame
        self.dead = False                           # set when its capture thread stops

    def _rotate(self):
        if self.writer:
            self.writer.close()
        self.part += 1
        path = os.path.join(self.folder, "audio", f"{self.key}-{self.part:03d}.wav")
        self.writer = sf.SoundFile(path, "w", samplerate=SR_DEV, channels=1, subtype="PCM_16")
        self.part_samples = 0

    def push(self, block48, now=None):
        if self.origin is None:
            self.origin = (now or time.time()) - len(block48) / SR_DEV
        if self.writer is None or self.part_samples >= PART_SECONDS * SR_DEV:
            self._rotate()
        self.writer.write(block48)
        self.part_samples += len(block48)
        x16 = resample_poly(block48, 1, 3).astype(np.float32)
        with self.lock:
            self.buf = np.concatenate([self.buf, x16])
            self.total += len(x16)
        self.rms_recent = float(np.sqrt(np.mean(block48 ** 2))) if len(block48) else 0.0
        return x16

    def close(self):
        if self.writer:
            self.writer.close()
            self.writer = None


class Live:
    def __init__(self, args):
        self.args = args
        self.out = os.path.abspath(args.out)
        for d in ("audio", "live"):
            os.makedirs(os.path.join(self.out, d), exist_ok=True)
        self.live = os.path.join(self.out, "live")
        self.t0 = time.time()
        self.started = datetime.now()
        self.mic = Channel("mic", args.me, self.out)
        self.rem = Channel("remote", args.remote, self.out)
        self.windows = queue.Queue()
        self.lines = []                   # (t_start, label, text)
        self.stop = threading.Event()
        self.asr_ready = threading.Event()
        self.segment_done = threading.Event()
        self.stats = {"windows": 0, "audio_s": 0.0, "asr_s": 0.0, "loops": 0, "lag_s": 0.0}
        self.events = open(os.path.join(self.live, "events.jsonl"), "a", encoding="utf-8")
        self.ev_lock = threading.Lock()
        self.transcript_path = os.path.join(self.live, "transcript.md")
        if not os.path.exists(self.transcript_path):
            with open(self.transcript_path, "w", encoding="utf-8") as f:
                f.write(f"# Transcription en direct : {args.title}\n\n"
                        f"Début : {self.started:%Y-%m-%d %H:%M}. Voix : {args.me} (micro), {args.remote} (sortie audio). "
                        "Texte brut d'un modèle local : à vérifier avant de citer.\n\n")
        with open(os.path.join(self.live, "labels.json"), "w", encoding="utf-8") as f:
            json.dump({"me": args.me, "remote": args.remote, "title": args.title, "echo_gate": args.echo_gate},
                      f, ensure_ascii=False)
        self.notes_path = os.path.join(self.live, "notes.md")
        if not os.path.exists(self.notes_path):
            with open(self.notes_path, "w", encoding="utf-8") as f:
                f.write("## Notes\n\n- En attente des premières minutes.\n")
        self.html_dirty = threading.Event()

    def event(self, **kw):
        kw["t"] = round(time.time() - self.t0, 2)
        with self.ev_lock:
            self.events.write(json.dumps(kw, ensure_ascii=False) + "\n")
            self.events.flush()

    def offsets(self):
        """Where sample 0 of each archive stream sits on the meeting clock, for the final pass."""
        return {f"{c.key}_offset_s": (round(c.origin - self.t0, 3) if c.origin else None) for c in (self.mic, self.rem)}

    def rel(self, ch, sample):
        """Seconds since the start of the recording, for a 16 kHz sample index of a channel."""
        return (ch.origin or self.t0) - self.t0 + sample / SR

    # ---------------- capture ----------------
    def capture(self, ch, device):
        try:
            with device.recorder(samplerate=SR_DEV, channels=1, blocksize=BLOCK) as r:
                while not self.stop.is_set():
                    data = r.record(numframes=BLOCK)
                    self.on_audio(ch, data[:, 0].astype(np.float32), time.time())
        except Exception as e:  # a device that disappears must not kill the other stream
            log(f"capture {ch.key} stopped: {e!r}")
            self.event(kind="capture_error", ch=ch.key, error=repr(e))
        finally:
            ch.rms_recent = 0.0          # a dead stream must not keep showing its last level
            ch.dead = True

    def on_audio(self, ch, block48, now=None):
        x16 = ch.push(block48, now)
        if ch is self.rem:  # remember when the remote side speaks, for the echo gate
            with ch.lock:
                done = len(ch.active) * FRAME
                avail = ch.total - done
                n = avail // FRAME
                if n:
                    tail = ch.buf[len(ch.buf) - avail:][: n * FRAME] if avail <= len(ch.buf) else None
                    if tail is not None and len(tail) == n * FRAME:
                        act = np.sqrt((tail.reshape(n, FRAME) ** 2).mean(axis=1)) > self.args.gate_threshold
                    else:
                        act = np.zeros(n, dtype=bool)
                    ch.active = np.concatenate([ch.active, act])
        return x16

    def simulate(self, path):
        from faster_whisper.audio import decode_audio
        a16 = decode_audio(path, sampling_rate=SR)
        s = int(self.args.sim_start * SR)
        e = len(a16) if self.args.sim_dur <= 0 else s + int(self.args.sim_dur * SR)
        a16 = a16[s:e]
        a48 = resample_poly(a16, 3, 1).astype(np.float32)
        log(f"simulation : {len(a16) / SR:.0f} s envoyés comme voix distantes, à x{self.args.sim_speed}")
        now = time.time()
        for i in range(0, len(a48), BLOCK):
            if self.stop.is_set():
                break
            blk = a48[i:i + BLOCK]
            self.on_audio(self.rem, blk, now)
            self.on_audio(self.mic, np.zeros(len(blk), dtype=np.float32), now)
            time.sleep(len(blk) / SR_DEV / self.args.sim_speed)
            now = time.time()
        log("simulation : fin du fichier")

    # ---------------- segmentation ----------------
    def gate_mic(self, start, x):
        """Silence the microphone where the remote side was speaking (echo from loudspeakers)."""
        if not self.args.echo_gate or self.rem.origin is None or self.mic.origin is None:
            return x
        with self.rem.lock:
            act = self.rem.active.copy()
        if not act.any():
            return x
        n = (len(x) + FRAME - 1) // FRAME
        # mic frame k starts at wall time mic.origin + (start + k*FRAME)/SR; map it to a remote frame
        wall0 = self.mic.origin + start / SR
        f = np.round((wall0 - self.rem.origin) * (SR / FRAME)).astype(int) + np.arange(n)
        before, after = 15, 25                              # remote active up to 0.5 s earlier or 0.3 s later
        c = np.concatenate([[0], np.cumsum(act.astype(np.int32))])
        lo = np.clip(f - after, 0, len(act))
        hi = np.clip(f + before + 1, 0, len(act))
        m = (c[hi] - c[lo]) > 0
        y = x.copy()
        y[np.repeat(m, FRAME)[: len(y)]] = 0.0
        return y

    def segment_loop(self):
        from faster_whisper.vad import VadOptions, get_speech_timestamps
        opts = VadOptions(threshold=0.5, min_silence_duration_ms=int(CLOSE_SIL * 1000), speech_pad_ms=200)
        maxw = int(MAX_WIN * SR)
        while True:
            time.sleep(1.0)
            final = self.stop.is_set()
            for ch in (self.mic, self.rem):
                with ch.lock:
                    buf, start = ch.buf.copy(), ch.buf_start
                if len(buf) < SR // 2 and not final:
                    continue
                x = self.gate_mic(start, buf) if ch is self.mic else buf
                spans = get_speech_timestamps(x, opts) if len(x) >= SR // 2 else []
                pieces = []                       # [a, b, forced]: a forced piece is a full 25 s cut
                for sp in spans:
                    a, b = sp["start"], sp["end"]
                    while b - a > maxw:
                        pieces.append([a, a + maxw, True])
                        a += maxw
                    if pieces and not pieces[-1][2] and a - pieces[-1][1] < SR and b - pieces[-1][0] <= maxw:
                        pieces[-1][1] = b         # merge across a short pause
                    else:
                        pieces.append([a, b, False])
                keep_from = len(x) if final else max(0, len(x) - SR)
                for i, (a, b, forced) in enumerate(pieces):
                    last = i == len(pieces) - 1
                    closed = final or forced or not last or b < len(x) - int(CLOSE_SIL * SR)
                    if closed:
                        self.emit(ch, start, x, a, b)
                        if last and not final:
                            keep_from = max(b, len(x) - SR) if b < len(x) - SR else b
                    else:
                        keep_from = a             # an open span stays for the next pass
                        break
                with ch.lock:
                    drop = min(keep_from, len(ch.buf))
                    ch.buf = ch.buf[drop:]
                    ch.buf_start += drop
            if final:
                break

    def emit(self, ch, start, x, a, b):
        if (b - a) < MIN_WIN * SR:
            return
        piece = x[a:b].copy()
        ts, te = self.rel(ch, start + a), self.rel(ch, start + b)
        self.windows.put((ch, ts, te, piece))
        self.event(kind="window", ch=ch.key, start=round(ts, 2), end=round(te, 2), queued=self.windows.qsize())

    # ---------------- transcription ----------------
    def load_model(self):
        import torch
        from transformers import AutoProcessor, CohereAsrForConditionalGeneration
        torch.set_num_threads(self.args.threads)
        t = time.time()
        self.processor = AutoProcessor.from_pretrained(REPO)
        try:
            self.model = CohereAsrForConditionalGeneration.from_pretrained(REPO, dtype=torch.bfloat16)
        except TypeError:
            self.model = CohereAsrForConditionalGeneration.from_pretrained(REPO, torch_dtype=torch.bfloat16)
        self.model.eval()
        self.torch = torch
        log(f"modèle prêt en {time.time() - t:.0f} s ({self.args.threads} threads)")
        self.asr_ready.set()

    def cap(self, piece):
        """Token budget scaled to the window: a window that hits it is looping."""
        return min(self.args.max_tokens, int(10 * len(piece) / SR) + 16)

    def transcribe(self, piece, max_tokens=None, **gen):
        # REUNION_LANG : langue de la réunion ("fr" pour une réunion en français) ; "ar" par défaut,
        # comme final_pass.py.
        inputs = self.processor(piece, sampling_rate=SR, return_tensors="pt",
                                language=os.environ.get("REUNION_LANG", "ar"))
        inputs.to(self.model.device, dtype=self.model.dtype)
        budget = max_tokens or self.cap(piece)
        with self.torch.inference_mode():
            try:
                ids = self.model.generate(**inputs, max_new_tokens=budget, **gen)
            except (TypeError, ValueError):   # a generation option this model does not take
                ids = self.model.generate(**inputs, max_new_tokens=budget)
        text = self.processor.decode(ids, skip_special_tokens=True)
        text = text[0] if isinstance(text, list) else text
        return text.strip(), int(ids.shape[-1]) >= budget

    @staticmethod
    def looks_looped(text):
        import zlib
        words = text.split()
        if len(words) < 12:
            return False
        raw = text.encode("utf-8")
        # Whisper's loop test uses 2.4, but Arabic in UTF-8 already compresses to about 2.1-2.5:
        # on the 20 Oct transcript, 2.4 flagged 7 % of normal lines. 3.0 keeps the real loops.
        if len(raw) > 200 and len(raw) / len(zlib.compress(raw)) > 3.0:
            return True
        for n in (1, 2, 3, 4, 5, 6):
            for i in range(0, len(words) - 4 * n + 1):
                g = words[i:i + n]
                if all(words[i + k * n:i + (k + 1) * n] == g for k in range(1, 4)):
                    return True
        return False

    def robust(self, piece):
        """Transcribe; on a loop, try the two halves, then the whole window with repetition limits."""
        text, hit = self.transcribe(piece)
        if not (hit or self.looks_looped(text)) or len(piece) < 4 * SR:
            return text, False
        h = len(piece) // 2
        a, _ = self.transcribe(piece[:h])
        b, _ = self.transcribe(piece[h:])
        halves = (a + " " + b).strip()
        if not self.looks_looped(halves):
            return halves, True
        c, _ = self.transcribe(piece, no_repeat_ngram_size=5, repetition_penalty=1.15)
        tries = [t for t in (halves, c, text) if not self.looks_looped(t)]
        return (min(tries, key=len) if tries else min((halves, c, text), key=len)), True

    def skip_backlog(self):
        """If the text falls more than about 90 s behind, jump to the newest windows. The skipped
        audio stays on disk and the final pass transcribes it; live, a placeholder line marks the gap."""
        if self.stop.is_set() or self.windows.qsize() <= 6:
            return
        old = []
        while self.windows.qsize() > 2:
            try:
                old.append(self.windows.get_nowait())
            except queue.Empty:
                break
        if old:
            ts, te = old[0][1], old[-1][2]
            self.stats["skipped_s"] = self.stats.get("skipped_s", 0) + sum(len(w[3]) for w in old) / SR
            line = f"[{hms(ts)}] *… passage de {hms(ts)} à {hms(te)} sauté en direct, repris dans la passe finale*"
            with open(self.transcript_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            self.lines.append((ts, "…", f"passage {hms(ts)}–{hms(te)} sauté en direct (passe finale)"))
            self.event(kind="skipped", start=round(ts, 2), end=round(te, 2), windows=len(old))
            log(f"retard : {len(old)} fenêtres sautées ({hms(ts)} à {hms(te)})")

    def asr_loop(self):
        self.load_model()
        while True:
            self.skip_backlog()
            try:
                ch, ts, te, piece = self.windows.get(timeout=0.5)
            except queue.Empty:
                if self.segment_done.is_set():
                    break
                continue
            t = time.time()
            text, looped = self.robust(piece)
            if looped:
                self.stats["loops"] += 1
            text, _cut = clean(text)
            dt = time.time() - t
            self.stats["windows"] += 1
            self.stats["audio_s"] += len(piece) / SR
            self.stats["asr_s"] += dt
            self.stats["lag_s"] = round(time.time() - (self.t0 + te), 1)
            if text:
                self.lines.append((ts, ch.label, text))
                with open(self.transcript_path, "a", encoding="utf-8") as f:
                    f.write(f"[{hms(ts)}] **{ch.label}** : {text}\n")
                self.html_dirty.set()
            self.event(kind="text", ch=ch.key, start=round(ts, 2), end=round(te, 2), asr_s=round(dt, 2),
                       lag_s=self.stats["lag_s"], looped=looped, chars=len(text))

    # ---------------- display ----------------
    def render(self):
        try:
            notes = open(self.notes_path, encoding="utf-8").read()
        except OSError:
            notes = ""

        def md(s):
            out = []
            for line in s.splitlines():
                e = html.escape(line)
                e = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", e)
                if line.startswith("#"):
                    out.append(f"<h3>{e.lstrip('# ')}</h3>")
                elif line.lstrip().startswith("- "):
                    out.append(f"<li>{e.lstrip()[2:]}</li>")
                elif line.strip():
                    out.append(f"<p>{e}</p>")
            return "\n".join(out)

        rows = "\n".join(
            f'<div class="line"><time>{hms(t)}</time><b class="{"me" if lab == self.args.me else "them"}">{html.escape(lab)}</b>'
            f'<span dir="auto">{html.escape(txt)}</span></div>'
            for t, lab, txt in reversed(self.lines[-400:]))
        el = time.time() - self.t0
        s = self.stats
        speed = (s["audio_s"] / s["asr_s"]) if s["asr_s"] else 0
        state = "modèle en chargement" if not self.asr_ready.is_set() else f"retard du texte {s['lag_s']:.0f} s"
        status = (f"{hms(el)} enregistrées, {state}, file {self.windows.qsize()}, vitesse x{speed:.1f}, "
                  f"niveaux micro {self.mic.rms_recent:.3f} / sortie {self.rem.rms_recent:.3f}")
        page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="5"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Réunion en direct</title><style>
:root {{ color-scheme: light; --ink:#14213d; --mute:#4a5568; --line:#e2e8f0; --rec:#c53030; --me:#2b6cb0; --them:#2f855a; }}
body {{ margin:0; font:15px/1.55 "Segoe UI", system-ui, sans-serif; color:var(--ink); background:#fff; }}
header {{ position:sticky; top:0; background:#fff; border-bottom:1px solid var(--line); padding:10px 16px; display:flex; gap:12px; align-items:baseline; flex-wrap:wrap; }}
.rec {{ color:var(--rec); font-weight:700; }} .status {{ color:var(--mute); font-size:13px; }}
main {{ display:grid; grid-template-columns:minmax(0,2fr) minmax(0,3fr); gap:24px; padding:16px; }}
@media (max-width:900px) {{ main {{ grid-template-columns:minmax(0,1fr); }} }}
.notes {{ background:#f7fafc; border:1px solid var(--line); border-radius:12px; padding:12px 16px; align-self:start; }}
.notes h3 {{ margin:12px 0 4px; font-size:15px; }} .notes li {{ margin:2px 0 2px 18px; }}
.line {{ display:grid; grid-template-columns:72px 130px minmax(0,1fr); gap:8px; padding:6px 0; border-bottom:1px solid var(--line); }}
time {{ font:13px/1.9 Consolas, monospace; color:var(--mute); }} b.me {{ color:var(--me); }} b.them {{ color:var(--them); }}
span {{ unicode-bidi:plaintext; }}
</style></head><body>
<header><span class="rec">● Enregistrement local en cours</span><strong>{html.escape(self.args.title)}</strong><span class="status">{html.escape(status)}</span></header>
<main><section class="notes">{md(notes)}</section><section><h3>Transcription (le plus récent en haut)</h3>{rows or "<p>En attente de la première phrase…</p>"}</section></main>
</body></html>"""
        tmp = os.path.join(self.live, "live.html.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(page)
        os.replace(tmp, os.path.join(self.live, "live.html"))
        st = {"elapsed_s": round(el, 1), "queue": self.windows.qsize(), "speed": round(speed, 2),
              "mic_rms": round(self.mic.rms_recent, 4), "remote_rms": round(self.rem.rms_recent, 4),
              "asr_ready": self.asr_ready.is_set(), "stopping": self.stop.is_set(),
              "mic_dead": self.mic.dead, "remote_dead": self.rem.dead, **self.offsets()}
        st.update({k: (round(v, 2) if isinstance(v, float) else v) for k, v in s.items()})
        tmp = os.path.join(self.live, "status.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f)
        os.replace(tmp, os.path.join(self.live, "status.json"))

    def html_loop(self):
        last_notes, last_beat = 0, 0
        while True:
            time.sleep(1.0)
            try:
                m = os.path.getmtime(self.notes_path)
            except OSError:
                m = 0
            if m != last_notes:
                last_notes = m
                self.html_dirty.set()
            if self.html_dirty.is_set() or time.time() - last_beat > 5:
                self.html_dirty.clear()
                last_beat = time.time()
                self.render()
            if not self.stop.is_set() and os.path.exists(os.path.join(self.out, "STOP")):
                log("fichier STOP trouvé : arrêt")
                self.stop.set()
            if self.stop.is_set() and self.segment_done.is_set() and self.windows.empty():
                break
        self.render()

    # ---------------- run ----------------
    def run(self):
        import soundcard as sc
        # Panne du 09/11 (entretien, mode A) : asr_loop importait torch et transformers dans
        # son thread pendant que les captures appelaient scipy.signal.resample_poly. scipy
        # (array_api_compat, _issubclass_fast) lit torch dans sys.modules alors qu'il n'est
        # qu'à moitié chargé : « partially initialized module 'torch' has no attribute
        # 'Tensor' », les deux captures s'arrêtaient à 0,5 s. Les charger ici, dans le thread
        # principal et avant tout thread, ferme la course (reproduit 3 fois sur 3 sans, 0 avec).
        import torch  # noqa: F401
        from transformers import AutoProcessor, CohereAsrForConditionalGeneration  # noqa: F401
        threads = []
        if self.args.simulate:
            threads.append(threading.Thread(target=self.simulate, args=(self.args.simulate,), daemon=True))
        else:
            mic = pick(sc.all_microphones(), self.args.mic) if self.args.mic else sc.default_microphone()
            spk = pick(sc.all_speakers(), self.args.speaker) if self.args.speaker else sc.default_speaker()
            loop = sc.get_microphone(id=str(spk.name), include_loopback=True)
            log(f"micro : {mic.name}")
            log(f"sortie : {spk.name} (loopback)")
            self.event(kind="devices", mic=mic.name, speaker=spk.name)
            threads.append(threading.Thread(target=self.capture, args=(self.mic, mic), daemon=True))
            threads.append(threading.Thread(target=self.capture, args=(self.rem, loop), daemon=True))
        seg = threading.Thread(target=self._segment, daemon=True)
        asr = threading.Thread(target=self.asr_loop, daemon=True)
        ui = threading.Thread(target=self.html_loop, daemon=True)
        for t in threads + [seg, asr, ui]:
            t.start()
        log(f"page en direct : {os.path.join(self.live, 'live.html')}")
        log("pour arrêter : créer le fichier STOP dans le dossier de la réunion, ou Ctrl+C")
        last = 0
        try:
            while not self.stop.is_set():
                time.sleep(1)
                if self.args.simulate and not threads[0].is_alive():
                    self.stop.set()
                if time.time() - last >= 30:
                    last = time.time()
                    s = self.stats
                    log(f"{hms(time.time() - self.t0)} file={self.windows.qsize()} fenêtres={s['windows']} retard={s['lag_s']}s "
                        f"micro={self.mic.rms_recent:.3f} sortie={self.rem.rms_recent:.3f} boucles={s['loops']}")
        except KeyboardInterrupt:
            log("Ctrl+C : arrêt")
            self.stop.set()
        log("arrêt : je termine les fenêtres en attente")
        seg.join(timeout=60)
        asr.join(timeout=1800)
        ui.join(timeout=15)
        for ch in (self.mic, self.rem):
            ch.close()
        s = self.stats
        summary = {"started": f"{self.started:%Y-%m-%d %H:%M:%S}", "duration_s": round(time.time() - self.t0, 1),
                   "mic_parts": self.mic.part, "remote_parts": self.rem.part, **self.offsets(), **s,
                   "speed": round(s["audio_s"] / s["asr_s"], 2) if s["asr_s"] else None}
        with open(os.path.join(self.live, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=1)
        self.render()
        log("terminé :", json.dumps(summary, ensure_ascii=False))

    def _segment(self):
        try:
            self.segment_loop()
        except Exception as e:
            log(f"segmentation stopped: {e!r}")
            self.event(kind="segment_error", error=repr(e))
            raise
        finally:
            self.segment_done.set()


def pick(devices, needle):
    for d in devices:
        if needle.lower() in d.name.lower():
            return d
    raise SystemExit(f"no device matches {needle!r}: {[d.name for d in devices]}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", help="meeting folder")
    p.add_argument("--title", default="Réunion")
    p.add_argument("--me", default="Moi", help="label of the microphone voice")
    p.add_argument("--remote", default="Participants", help="label of the voices from the system output")
    p.add_argument("--mic", help="part of the microphone name (default: system default)")
    p.add_argument("--speaker", help="part of the output device name (default: system default)")
    p.add_argument("--threads", type=int, default=12)
    p.add_argument("--max-tokens", type=int, default=256)
    p.add_argument("--gate-threshold", type=float, default=0.004, help="RMS above which the remote side counts as speaking")
    p.add_argument("--no-echo-gate", dest="echo_gate", action="store_false",
                   help="keep the microphone while the others speak (use with headphones)")
    p.add_argument("--list-devices", action="store_true")
    p.add_argument("--simulate", help="feed an audio file as the remote stream instead of the devices")
    p.add_argument("--sim-start", type=float, default=0)
    p.add_argument("--sim-dur", type=float, default=180)
    p.add_argument("--sim-speed", type=float, default=1.0)
    a = p.parse_args()
    if a.list_devices:
        import soundcard as sc
        print("Micros :", *[f"  {m.name}" for m in sc.all_microphones()], sep="\n")
        print("Sorties :", *[f"  {s.name}" for s in sc.all_speakers()], sep="\n")
        print("Par défaut :", sc.default_microphone().name, "|", sc.default_speaker().name)
        return
    if not a.out:
        p.error("--out is required")
    Live(a).run()


if __name__ == "__main__":
    main()
