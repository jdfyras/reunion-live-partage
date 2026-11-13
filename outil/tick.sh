#!/usr/bin/env bash
# Heartbeat for the note taker (Claude Code Monitor). Every N seconds, if the live transcript grew
# past the offset stored in live/notes.offset, print "TICK lignes A-B". Print "ALERTE ..." at once
# when something breaks, and "FIN" when the meeting folder gets a STOP file.
# The offset is written by the note taker after it has read the lines, so a re-armed watch never
# replays what was already read.
# Usage: bash tick.sh "<meeting folder>" [seconds, default 45]
d="$1"; every="${2:-45}"
t="$d/live/transcript.md"; off="$d/live/notes.offset"; st="$d/live/status.json"; ev="$d/live/events.jsonl"
count_err() { local c; c=$(grep -c '_error' "$ev" 2>/dev/null); echo "${c:-0}"; }
start=$(date +%s); seen_err=$(count_err); alerted=""
while true; do
  [ -f "$d/STOP" ] && { echo "FIN"; exit 0; }
  now=$(date +%s)
  # alerts
  if [ -f "$st" ]; then
    age=$(( now - $(stat -c %Y "$st") ))
    [ "$age" -gt 30 ] && [ "$alerted" != "stale" ] && { echo "ALERTE status.json ne bouge plus depuis ${age} s : la fenêtre de l'outil est peut-être fermée"; alerted="stale"; }
    s=$(cat "$st")
    case "$s" in *'"asr_ready": false'*) [ $(( now - start )) -gt 90 ] && [ "$alerted" != "asr" ] && { echo "ALERTE le modèle n'est pas prêt après 90 s"; alerted="asr"; } ;; esac
    case "$s" in *'"mic_dead": true'*) [ "$alerted" != "mic" ] && { echo "ALERTE la piste micro s'est arrêtée"; alerted="mic"; } ;; esac
    case "$s" in *'"remote_dead": true'*) [ "$alerted" != "remote" ] && { echo "ALERTE la piste des autres s'est arrêtée"; alerted="remote"; } ;; esac
    lag=$(printf '%s' "$s" | sed -n 's/.*"lag_s": \([0-9.]*\).*/\1/p'); q=$(printf '%s' "$s" | sed -n 's/.*"queue": \([0-9]*\).*/\1/p')
    if [ -n "$lag" ] && [ "${lag%.*}" -gt 120 ] && [ "$alerted" != "lag" ]; then echo "ALERTE retard du texte ${lag} s"; alerted="lag"; fi
    if [ -n "$q" ] && [ "$q" -gt 10 ] && [ "$alerted" != "queue" ]; then echo "ALERTE file d'attente ${q} fenêtres"; alerted="queue"; fi
  fi
  e=$(count_err)
  [ "$e" -gt "$seen_err" ] && { echo "ALERTE erreur dans events.jsonl : $(grep '_error' "$ev" | tail -1 | cut -c1-200)"; seen_err=$e; }
  # new lines
  if [ -f "$t" ]; then
    n=$(wc -l < "$t"); a=$(cat "$off" 2>/dev/null || echo 0)
    [ "$n" -gt "$a" ] && echo "TICK lignes $((a + 1))-$n"
  fi
  sleep "$every"
done
