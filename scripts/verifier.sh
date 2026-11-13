#!/usr/bin/env bash
# Après l'arrêt : chaque partie se relit-elle, et combien de temps dure-t-elle ?
# ffprobe répond "N/A" sur un fichier tué en cours d'écriture ; seul un décodage complet donne la durée.
# Usage : bash verifier.sh [prefixe]
prefixe="${1:-$HOME/reunion-$(date +%F)}"
for f in "$prefixe".mka "$prefixe"-partie*.mka; do
  [ -e "$f" ] || continue
  t=$(ffmpeg -v error -stats -i "$f" -f null - 2>&1 | tr '\r' '\n' | grep -o 'time=[0-9:.]*' | tail -1)
  echo "$(basename "$f") : ${t:-ILLISIBLE}"
done
