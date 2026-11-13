"""Measure a Whisper fine-tune (default: oddadmix/Whisperv3-tunisian-codeswitch) on CPU.

Usage: python test_whisper_tn.py <audio file> <start s> <duration s> <out.txt> [repo] [threads]
Cuts the stretch into VAD windows of at most 28 s, transcribes each with the card's settings
(language ar, transcribe, greedy, 256 new tokens), prints the real-time factor.
"""
import sys
import time

import torch
from faster_whisper.audio import decode_audio
from faster_whisper.vad import VadOptions, get_speech_timestamps
from transformers import WhisperForConditionalGeneration, WhisperProcessor

SR = 16000
audio, start, dur, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
repo = sys.argv[5] if len(sys.argv) > 5 else "oddadmix/Whisperv3-tunisian-codeswitch"
torch.set_num_threads(int(sys.argv[6]) if len(sys.argv) > 6 else 16)
sys.stdout.reconfigure(encoding="utf-8")

t = time.time()
proc = WhisperProcessor.from_pretrained(repo)
model = WhisperForConditionalGeneration.from_pretrained(repo, dtype=torch.bfloat16)
model.eval()
print(f"model loaded in {time.time() - t:.0f} s", flush=True)

a = decode_audio(audio, sampling_rate=SR)[int(start * SR):int((start + dur) * SR)]
spans = get_speech_timestamps(a, VadOptions(threshold=0.5, min_silence_duration_ms=500, speech_pad_ms=300))
wins = []
for s in spans:
    x, y = s["start"] / SR, s["end"] / SR
    while y - x > 28:
        wins.append([x, x + 28]); x += 28
    if wins and y - wins[-1][0] <= 28 and x - wins[-1][1] < 2.0:
        wins[-1][1] = y
    else:
        wins.append([x, y])

t = time.time()
lines = []
with torch.inference_mode():
    for x, y in wins:
        feats = proc(a[int(x * SR):int(y * SR)], sampling_rate=SR, return_tensors="pt").input_features.to(torch.bfloat16)
        ids = model.generate(feats, language="ar", task="transcribe", max_new_tokens=256)
        lines.append(f"[{start + x:7.1f}] {proc.batch_decode(ids, skip_special_tokens=True)[0].strip()}")
        print(f"  window {x:6.1f}-{y:6.1f} done at {time.time() - t:.0f} s", flush=True)
el = time.time() - t
speech = sum(y - x for x, y in wins)
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"{speech:.0f} s of speech in {el:.0f} s: x{speech / el:.2f} real time, {len(wins)} windows", flush=True)
