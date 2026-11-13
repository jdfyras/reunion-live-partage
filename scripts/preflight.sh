#!/usr/bin/env bash
# Avant de lancer : périphériques audio, mémoire libre, modèle conseillé, nom de la prochaine partie.
# Usage : bash preflight.sh [prefixe]      (prefixe par défaut : $HOME/reunion-AAAA-MM-JJ)
prefixe="${1:-$HOME/reunion-$(date +%F)}"

echo "== Périphériques audio (dshow)"
ffmpeg -hide_banner -list_devices true -f dshow -i dummy 2>&1 | grep '(audio)' | sed -E 's/.*"(.*)" \(audio\)/  \1/'

echo "== Mémoire libre"
libre_ko=$(powershell -NoProfile -Command "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory" | tr -d '\r')
libre_go=$(awk "BEGIN{printf \"%.1f\", $libre_ko/1048576}")
echo "  $libre_go Go"
if awk "BEGIN{exit !($libre_ko >= 2621440)}"; then
  echo "  modele conseille : small"
elif awk "BEGIN{exit !($libre_ko >= 1048576)}"; then
  echo "  modele conseille : base (RAM juste, small risque de faire couper l'enregistrement)"
else
  echo "  modele conseille : AUCUN (moins de 1 Go : enregistrer seulement, transcrire apres)"
fi

nb_py=$(powershell -NoProfile -Command "(Get-Process python* -ErrorAction SilentlyContinue | Measure-Object).Count" | tr -d '\r')
echo "  processus Python en cours : $nb_py (au-delà d'une dizaine : sans doute des serveurs MCP d'anciennes sessions Claude)"

echo "== Prochaine partie"
if [ ! -e "$prefixe.mka" ]; then echo "  $prefixe.mka"
else n=2; while [ -e "$prefixe-partie$n.mka" ]; do n=$((n+1)); done; echo "  $prefixe-partie$n.mka"; fi

echo "== Python faster-whisper"
py="$(cd "$(dirname "$0")/.." && pwd)/outil/.venv/Scripts/python.exe"
[ -x "$py" ] && echo "  $py" || echo "  INTROUVABLE : $py"
