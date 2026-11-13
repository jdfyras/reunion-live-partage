"""Transcription au fil de l'eau d'un enregistrement en cours d'écriture.

Usage : python live.py <audio.mka> [modele]        (modele : small par défaut, base si la RAM manque)

Toutes les INTERVALLE secondes, extrait la partie nouvelle du fichier audio, la transcrit
avec faster-whisper et l'ajoute à <audio>.live.txt, une ligne "[mm:ss] texte" par segment.

Filtres, nés de la première séance réelle (voir nettoyer()) :
- Whisper répète parfois une phrase courte sur deux ou trois segments consécutifs
  ("Ça va? Ça va? Ça va?") : on saute un segment identique à l'un des trois précédents ;
- sur un son faible, Whisper boucle, d'un segment à l'autre ("Et. Et. Et.") ou dans un même
  segment ("Teste Teste Teste Teste", surtout avec base) : condition_on_previous_text=False
  limite l'emballement, et on réduit un mot répété à deux occurrences.
"""
import os
import re
import subprocess
import sys
import time
import wave
from collections import deque

INTERVALLE = 45
REPETITION = re.compile(r"\b(\w+)(?:[\s,.]+\1\b){2,}", re.IGNORECASE)
# Réunions en français : un caractère coréen, chinois ou japonais est toujours une invention.
HORS_ALPHABET = re.compile(r"[぀-ヿ㐀-鿿가-힯]+")


def nettoyer(texte, recents):
    """Texte à écrire, ou None pour sauter le segment. Met `recents` à jour."""
    texte = HORS_ALPHABET.sub("", texte)
    texte = REPETITION.sub(r"\1 \1…", texte.strip())
    cle = texte.lower().strip(".,!?… ")
    if not cle or cle in recents:
        return None
    recents.append(cle)
    return texte


def main():
    from faster_whisper import WhisperModel

    source = sys.argv[1]
    modele = sys.argv[2] if len(sys.argv) > 2 else "small"
    base = os.path.splitext(source)[0]
    sortie = base + ".live.txt"
    tmp = base + ".chunk.wav"

    model = WhisperModel(modele, device="cpu", compute_type="int8")
    offset = 0.0
    recents = deque(maxlen=3)

    while True:
        time.sleep(INTERVALLE)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{offset}",
                        "-i", source, "-ac", "1", "-ar", "16000", tmp], check=False)
        try:
            with wave.open(tmp) as w:
                duree = w.getnframes() / w.getframerate()
        except Exception:
            continue
        if duree < 5:
            continue
        segments, _ = model.transcribe(tmp, language="fr", vad_filter=True, beam_size=1,
                                       condition_on_previous_text=False)
        with open(sortie, "a", encoding="utf-8") as f:
            for s in segments:
                texte = nettoyer(s.text, recents)
                if texte is None:
                    continue
                t = offset + s.start
                f.write(f"[{int(t // 60):02d}:{int(t % 60):02d}] {texte}\n")
        offset += duree


if __name__ == "__main__":
    main()
