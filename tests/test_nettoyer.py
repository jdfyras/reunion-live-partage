"""Tests du filtre de transcription, sur des lignes réelles de la séance du 2026-10-01.

Lancer : python tests/test_nettoyer.py      (aucune dépendance : faster-whisper n'est pas importé)
"""
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from live import nettoyer  # noqa: E402


def passe(lignes):
    recents = deque(maxlen=3)
    return [t for t in (nettoyer(l, recents) for l in lignes) if t is not None]


def test_doublons_consecutifs():
    # Whisper répète une phrase courte sur plusieurs segments (lignes réelles du 2026-10-01).
    lignes = ["Bonjour, bonjour.", "Alors, c'est moi.", "Ça va?", "Ça va?", "Ça va?",
              "C'est moi.", "C'est moi."]
    assert passe(lignes) == ["Bonjour, bonjour.", "Alors, c'est moi.", "Ça va?", "C'est moi."]


def test_boucle_entre_segments():
    assert passe(["Et."] * 9) == ["Et."]


def test_boucle_dans_un_segment():
    assert nettoyer("Teste Teste Teste Teste Teste Buzen", deque(maxlen=3)) == "Teste Teste… Buzen"


def test_alphabet_invente_retire():
    assert "그래요" not in nettoyer("des 그래요, on avance", deque(maxlen=3))


def test_repetitions_legitimes_intactes():
    for t in ["ça doit aller très très vite", "nous nous sommes vus", "C'est bien, c'est bien."]:
        assert nettoyer(t, deque(maxlen=3)) == t, t


def test_une_phrase_redite_plus_tard_est_gardee():
    # La fenêtre est de trois segments : une vraie reprise plus loin n'est pas perdue.
    lignes = ["Ok.", "a", "b", "c", "Ok."]
    assert passe(lignes) == lignes


if __name__ == "__main__":
    tests = [f for n, f in sorted(globals().items()) if n.startswith("test_")]
    for f in tests:
        f()
        print("ok  ", f.__name__)
    print(f"{len(tests)} tests passés")
