# reunion-live (outil)

Enregistre une réunion en local et la transcrit pendant qu'elle a lieu, y compris en darja
tunisienne mêlée de français et d'anglais. C'est le mode A du skill `reunion-live`
(`~\.claude\skills\reunion-live\SKILL.md`), qui pilote l'outil, souffle les répliques et rédige
le compte rendu.

## Ce qui tourne

- **Deux pistes séparées :**
  - le micro par défaut de Windows : ta voix ;
  - la sortie audio par défaut, lue en WASAPI loopback : les autres participants d'un Google Meet, d'un Zoom ou d'un Teams. C'est une copie numérique, mesurée le 21/10.
- **Un filtre d'écho.** Sur haut-parleurs, ton micro entend aussi les autres. Quand la sortie parle, le micro est coupé pour la transcription ; l'audio brut reste intact. Avec un casque, mets `--no-echo-gate`.
- **Le découpage.** Silero VAD (via faster-whisper) découpe des fenêtres de 20 s au plus.
- **Le modèle de transcription.** Cohere Transcribe Arabic (`CohereLabs/cohere-transcribe-arabic-07-2026`), en bf16 sur CPU, 12 threads, environ 7 Go de mémoire. Il va 8 à 9 fois plus vite que le temps réel. Une boucle se rattrape en deux temps : les deux moitiés de la fenêtre, puis la fenêtre entière avec `no_repeat_ngram_size=5` et `repetition_penalty=1.15`. `textclean.py` coupe ensuite les répétitions et le texte inventé sur du silence.
- **Une page `live/live.html`** rafraîchie toutes les 5 s. Elle montre « ● Enregistrement local en cours », les notes (`live/notes.md`, écrites par Claude) et la transcription, la plus récente en haut.

Rien ne sort de la machine.

## Installer (une fois)

Windows, PowerShell 7, Python 3.12 et ffmpeg dans le PATH. Depuis ce dossier `outil\` :

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.1 torchaudio==2.11.0
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Les deux modèles se téléchargent depuis Hugging Face au premier lancement (plusieurs Go) :
`CohereLabs/cohere-transcribe-arabic-07-2026` pour la transcription, et
`pyannote/speaker-diarization-community-1` pour la passe finale. Si le téléchargement est refusé,
ouvre la page du modèle sur Hugging Face, accepte ses conditions, puis connecte la machine avec
`.venv\Scripts\hf.exe auth login`.

Compte 16 Go de mémoire vive au moins : le modèle en prend environ 7.

Non vérifié : cette installation n'a pas été rejouée sur une machine vierge. Les versions de
`requirements.txt` sont celles de la machine d'origine.

## Lancer

```powershell
pwsh -File .\start-meeting.ps1 -Out "<dossier>" -Title "Kickoff" -Me "<ton prénom>" -Remote "<les autres>"
```

Options :
- `-Headphones` si tu portes un casque ;
- `-Speaker "<partie du nom>"` si le son du call sort ailleurs que sur la sortie par défaut.

Pour voir les périphériques :
`.venv\Scripts\python.exe -X utf8 reunion_live.py --list-devices`.

Arrêter : crée le fichier `STOP` dans le dossier de la réunion, ou fais Ctrl+C dans la fenêtre.

Simuler sans micro, avec un fichier audio rejoué comme voix distantes :

```powershell
pwsh -File start-meeting.ps1 -Out "<dossier de test>" -Simulate "<audio>" -SimStart 600 -SimDur 120
```

## Après la réunion

```powershell
.venv\Scripts\python.exe -X utf8 final_pass.py "<dossier>" --remote-speakers 2
```

La passe finale reprend les fichiers complets :
- elle sépare d'abord les voix de la sortie du PC avec pyannote (« Voix 1 », « Voix 2 »), dans la version sans chevauchement ;
- elle coupe les fenêtres de cette piste le long des tours de parole, une seule voix par fenêtre et 28 s au plus ;
- pour le micro, elle coupe les fenêtres par VAD ;
- elle refait la transcription et écrit `final/transcript.final.md`.

Mesuré le 21/10 : 3 minutes d'audio en 2 minutes, dont 1 min 35 pour pyannote. Compte 30 à 40 minutes pour une heure de réunion.

## Dossier d'une réunion

```
audio/mic-001.wav, remote-001.wav …   48 kHz, tranches de 5 minutes
live/transcript.md                    une ligne par fenêtre : [hh:mm:ss] **voix** : texte
live/notes.md, live/live.html         notes et page en direct
live/status.json, live/summary.json   état (niveaux, retard, vitesse), bilan à l'arrêt
live/events.jsonl, live/labels.json   journal des fenêtres, étiquettes des voix
final/                                passe finale et compte rendu
recorder.log                          sortie de la fenêtre
```

## Pièges

- **numpy.** `soundcard` 0.4.5 appelle `numpy.fromstring`, que numpy 2 a supprimé. Le script le corrige au démarrage.
- **av.** `av` 19 casse le décodage de faster-whisper : le venv fixe `av==18.1.0`.
- **PowerShell et `python.exe`.** PowerShell lit la sortie de Python en CP850 : `start-meeting.ps1` force l'UTF-8.
- **Changement de sortie audio.** Un casque Bluetooth branché pendant la réunion change la sortie par défaut, et la piste « autres » devient muette. Il faut relancer dans un nouveau dossier.
- **Coupure de la fenêtre.** Si elle se ferme, l'audio jusqu'à la coupure reste dans `audio/`, et `final_pass.py` lit aussi une tranche restée ouverte.
