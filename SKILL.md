---
name: reunion-live
description: >
  Accompagner l'utilisateur pendant une réunion en direct : enregistrer la réunion en local,
  transcrire en temps réel sur CPU, y compris la darja tunisienne mêlée de français et
  d'anglais, suivre la transcription au fil de l'eau et lui souffler des suggestions courtes
  adaptées au contexte du projet et à la mémoire de la session (quoi dire, quoi demander,
  quand se taire). Tenir des notes visibles en direct, puis faire la passe finale qui sépare
  les voix et le compte rendu (décisions, actions, dates, ce qui le concerne). À utiliser dès
  que l'utilisateur dit qu'il entre en réunion, qu'il a une réunion dans quelques minutes, qu'il veut
  transcrire, enregistrer ou suivre une réunion, un call, un Google Meet, un point d'équipe,
  un rendez-vous client ou un webinar en direct, ou qu'il veut de l'aide, des réponses ou un
  coaching pendant qu'il parle — même s'il ne prononce pas le mot « transcription », et même
  si la réunion est en darja. Aussi quand il écrit « stop » ou « relance » au sujet d'un
  enregistrement en cours, ou demande le compte rendu d'une réunion enregistrée.
---

# Réunion en direct

Deux chemins. **Le mode A est celui par défaut depuis le 21/10.**

**Mode A : deux pistes et Cohere**, pour la darja, le français et l'anglais :

```
micro ─────────┐                         ┌─> live/transcript.md ──Monitor──> toi ──> répliques + live/notes.md
               ├─ reunion_live.py ───────┤          (page live/live.html, rafraîchie toutes les 5 s)
sortie du PC ──┘   (VAD + Cohere)        └─> audio/*.wav ── « stop » ──> final_pass.py ──> compte rendu
```

L'outil est dans `<skill>\outil\`, où `<skill>` désigne le dossier de ce fichier (en général
`~\.claude\skills\reunion-live`). Il a son propre venv (`<skill>\outil\.venv`), et son `README.md`
détaille l'installation et les options.

**Mode B, de secours : micro seul et faster-whisper.** C'est la chaîne du 01/10 :

```
micro ──ffmpeg──> partie.mka ──live.py (45 s)──> partie.live.txt ──Monitor──> toi ──> suggestions
```

Ses scripts sont dans `scripts/`, à côté de ce fichier. Il utilise le même venv,
`<skill>\outil\.venv`, qui contient faster-whisper.

Prends le mode B :
- quand il reste moins de 8 Go de mémoire libre (Cohere en prend environ 7) ;
- ou pour une réunion 100 % en français sans la mémoire nécessaire.

Tout est local : l'audio ne sort jamais de la machine. La machine n'a pas de GPU, tout tourne
en CPU, et c'est la **mémoire vive** qui casse la chaîne, pas le CPU (voir « Coupures »).

## 1. Démarrer — vite, la réunion commence

L'utilisateur a souvent deux minutes. Ne pose pas de question avant d'avoir lancé l'enregistrement :
le contexte se récupère après, une minute d'audio perdue ne se récupère pas.

### Mode A (par défaut)

1. `pwsh -File <skill>\outil\preflight.ps1` : mémoire libre et marge
   d'engagement, plus gros consommateurs, Ollama, noms des périphériques.
   - Il faut viser 10 Go libres et 12 Go de marge. Ce qui libère le plus : les autres sessions
     Claude Code (avec leurs serveurs MCP), les onglets Chrome inutiles, et WSL (`wsl --shutdown`,
     qui arrête aussi Docker), à demander à l'utilisateur.
   - Sous 8 Go libres : mode B.
2. **Le dossier de la réunion.** Pour un projet, prends son dossier privé de réunions
   (`<projet>\_Réunions (privé)\AAAA-MM-JJ <nom>\`) ; sinon, `~\reunion-AAAA-MM-JJ <nom>\`.
   Ne réutilise jamais un dossier qui contient déjà `audio\`.
3. **Lancer l'outil dans sa propre fenêtre**, pas en tâche de fond de Claude Code : une fenêtre
   à part ne peut pas être coupée quand la mémoire manque (voir « Coupures »). PowerShell :
   ```powershell
   $l = '<skill>\outil\start-meeting.ps1'
   Start-Process (Get-Command pwsh).Source -WindowStyle Minimized -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',"`"$l`"",'-Out',"`"<dossier>`"",'-Title','"<titre>"','-Me','"<son prénom>"','-Remote','"<les autres>"')
   ```
   - Chaque argument qui contient un espace porte ses propres guillemets : `Start-Process`
     colle les arguments sans les citer.
   - **Épingle les deux périphériques par leur nom**, sans « par défaut » : `-Mic "<nom du micro>"` et
     `-Speaker "<sortie où Meet joue le son>"`. Un casque Bluetooth qui se connecte peut sinon
     devenir le micro par défaut, en qualité téléphone.
   - `-Headphones` si l'utilisateur porte un casque. Sans casque, le filtre d'écho coupe son micro
     pendant que les autres parlent.
   - **Le secours**, dans une deuxième fenêtre :
     `backup-mic.ps1 -Out "<dossier>"`, lancé de la même façon que `start-meeting.ps1`.
     Il enregistre le micro seul, avec ffmpeg en Matroska + FLAC, flushé chaque seconde, et
     s'arrête avec le même fichier `STOP`. Sur haut-parleurs, il entend aussi les autres.
4. **Ouvrir la page** pour l'utilisateur : `Start-Process "<dossier>\live\live.html"`. Elle affiche
   « ● Enregistrement local en cours », les notes, et la transcription, la plus récente en haut.
5. **Vérifier, 30 à 60 s après le lancement**, dans `live\status.json` :
   - `asr_ready` doit valoir `true` (le modèle charge en 5 à 30 s) ;
   - `mic_rms` doit dépasser 0,002 quand l'utilisateur parle ;
   - `remote_rms` doit dépasser 0,002 quand un autre parle.

   Une piste muette se règle tout de suite, avec `--list-devices` puis une relance dans un
   nouveau dossier.
6. **Armer le Monitor** (`timeout_ms: 1800000`) sur le battement :
   `bash "<skill>/outil/tick.sh" "<dossier>" 45`
   - Toutes les 45 s, il écrit `TICK lignes A-B` s'il y a des lignes nouvelles depuis
     `live\notes.offset`.
   - Il écrit `ALERTE …` tout de suite dans ces cas : une piste arrêtée, `status.json` figé, le modèle pas prêt après 90 s, un retard au-delà de 120 s, une file au-delà de 10 fenêtres, une erreur dans `events.jsonl`.
   - Il écrit `FIN` quand `STOP` existe.

   **À chaque TICK :**
   1. Lis les lignes A à B de `live\transcript.md`.
   2. Donne la lecture et la réplique éventuelle (section 3).
   3. Mets à jour `notes.md` si besoin.
   4. Écris B dans `live\notes.offset`.

   Un battement réarmé ne rejoue donc jamais ce qui a été lu.
7. Dire en trois lignes ce qui tourne, où est la page, et les commandes :
   « ? », « réponds à X », « stop ».

**Capture mesurée le 21/10, sur la machine d'origine.** La sortie du PC est lue en WASAPI
loopback, sur la sortie par défaut. C'est une copie numérique : une sinusoïde jouée à 0,05 est
captée à 0,05 exactement. Les voix d'un Google Meet arrivent donc propres, sans passer par le
micro. Le « Mixage stéréo » Realtek reste inutile (voir le mode B).

**Réglages du direct (recherche du 21/10).**
- Le modèle est Cohere Transcribe Arabic, avec `language="ar"`, en glouton.
- Les fenêtres VAD font 20 s au plus.
- Une boucle se voit à trois signes : le plafond de tokens atteint, une répétition, ou une compression au-delà de 3,0. On relance alors les deux moitiés, puis la fenêtre entière avec `no_repeat_ngram_size=5` et `repetition_penalty=1.15`.
- Vitesse mesurée : 8 à 9 fois le temps réel sur 12 threads. Le texte arrive 2 à 20 s après la fin d'une phrase.
- Le français et l'anglais sortent souvent en lettres arabes. Corrige-les dans tes lectures quand c'est sûr.
- Si le texte prend plus d'environ 90 s de retard (plus de 6 fenêtres en attente), l'outil saute aux fenêtres les plus récentes. Il écrit une ligne « passage … sauté en direct, repris dans la passe finale » : l'audio reste sur le disque.
- Le modèle LINAGORA (`linagora/linto-asr-ar-tn-0.1`, Vosk) a été écarté le 21/10 : il perdait plus de la moitié des mots sur un enregistrement de test. Il n'est pas fourni.

### Mode B (secours : micro seul)

1. `bash scripts/preflight.sh` : noms exacts des périphériques audio, mémoire libre, modèle
   conseillé, nom de la prochaine partie (on ne réécrit jamais une partie existante).
2. Lancer l'enregistrement (Bash, `run_in_background: true`, `timeout: 7200000`), **micro seul** :
   ```bash
   ffmpeg -hide_banner -nostdin -y -f dshow -i audio="<micro>" \
     -ac 1 -ar 16000 -c:a flac "<partie>.mka" 2> "<partie>.ffmpeg.log"
   ```
   Matroska + FLAC parce qu'un fichier tué en cours d'écriture reste lisible.

   **Pourquoi pas le « Mixage stéréo »** (mesuré le 2026-10-01, sur la machine d'origine) : le son y sort
   par les écrans (audio AMD en HDMI/DP), pas par la carte Realtek. Le « Mixage stéréo »
   Realtek n'enregistre donc que du silence numérique (-91 dB), et le mélanger au micro avec
   `amix` divise le niveau du micro par deux. Les voix des autres participants arrivent
   uniquement par le micro de la webcam, qui entend les écrans : 86 % de mots justes sur un
   texte de test lu par le haut-parleur. Ne réintroduire le « Mixage stéréo » que si la sortie
   audio par défaut passe par la Realtek, après avoir vérifié qu'il capte bien un son joué
   (`-af volumedetect` doit donner bien mieux que -90 dB).
3. Vérifier que ça capte : `tail -c 200 <partie>.ffmpeg.log` doit montrer `time=` qui avance.
4. Lancer la transcription (Bash, arrière-plan) avec le modèle conseillé :
   `"<python du venv>" scripts/live.py "<partie>.mka" <small|base>`
   avec `PYTHONIOENCODING=utf-8 HF_HUB_DISABLE_XET=1` (le backend Xet se fige ici).
5. Armer le Monitor (`timeout_ms: 1800000`) :
   `f="<partie>.live.txt"; until [ -f "$f" ]; do sleep 2; done; tail -n +1 -f "$f"`
6. Dire en trois lignes ce qui tourne, où sont les fichiers, et les commandes :
   « ? », « réponds à X », « stop ».

## 2. Charger le contexte — pendant que le premier bloc arrive (~1 min)

Les suggestions ne valent que par le contexte. Pendant l'attente du premier bloc :

- Relire l'index mémoire déjà en contexte et ouvrir les fiches liées au sujet probable
  (projet, client, personnes). Le CLAUDE.md global donne les conventions de travail.
- Si le répertoire courant est un projet, regarder rapidement son README, les tickets ou
  la branche en cours : c'est là que se trouvent les faits que l'utilisateur pourra citer.
- Ne pas interroger l'utilisateur maintenant ; il est en train de parler. Le contexte se déduit de
  la transcription (ordre du jour annoncé, prénoms, sujets) et s'enrichit au fil de l'eau.

Tiens à jour, dans ta tête ou dans un fichier du scratchpad, une fiche courte : participants
et rôles devinés, ordre du jour, décisions, actions avec responsable, dates, questions
adressées à l'utilisateur. Elle nourrit les suggestions et deviendra le compte rendu.

## 3. Suivre et suggérer

Chaque événement du Monitor est un bloc de transcription, pas un message de l'utilisateur. Lis
`references/coaching.md` avant la première suggestion : il contient les règles qui ont
fait la différence en séance réelle. L'essentiel :

- **Une ligne de lecture par bloc**, puis une suggestion seulement si elle change ce que
  l'utilisateur dirait maintenant. Bloc sans intérêt → une phrase, ou rien.
- La transcription est mauvaise par endroits. Ne surinterprète pas ; dis « mal transcrit »
  et passe. Ne présente jamais une déduction comme ce qui a été dit.
- On ne sait pas qui parle. Quand un « toi » peut viser l'utilisateur, dis-le au conditionnel.
- **Quand l'utilisateur est nommé ou qu'on lui pose une question**, c'est le moment le plus utile :
  propose une réponse prête à dire, courte, avec un livrable et une date. Envoie aussi une
  `PushNotification` — il ne regarde peut-être pas l'écran.
- Ne lui fais jamais jouer plus de deux interventions de fond par réunion ; rappelle-le si
  tu en as déjà proposé beaucoup.
- **Ne souffle jamais un numéro de ticket, une cause ou une capacité produit que tu n'as pas
  lus dans la session.** Sinon, pose-le en question. Voir la règle du 01/10 dans `coaching.md`.
- Préférences de l'utilisateur (explication FR et AR de chaque sujet, une seule réplique qui
  challenge et propose, mots simples pour un public non technique) : voir `coaching.md`.

**En mode A**, chaque événement est une ligne `[hh:mm:ss] **<voix>** : <texte>`. La voix est
celle de la piste : `--me` pour le micro, `--remote` pour la sortie du PC. Tu sais donc quand
l'utilisateur parle. La darja est écrite en lettres arabes par la machine : lis-la pour le sens, et
cite-la le moins possible.

Toutes les 5 minutes environ, et dès qu'une décision ou une action tombe, réécris
`<dossier>\live\notes.md` en entier. La page l'affiche à gauche. Les notes sont courtes, en
français, avec `[hh:mm:ss]`, sous quatre titres :
- `## Décisions` : seulement ce qui est dit comme décidé ; un exemple reste un exemple ;
- `## Actions` : qui, quoi, pour quand ;
- `## Questions ouvertes` ;
- `## À vérifier` : les passages incertains, avec `[?]`.

Ces notes deviennent la fiche du compte rendu.

Le Monitor expire après 30 minutes : réarme-le aussitôt, avec `tail -n 0 -f` pour ne pas
rejouer ce qui a déjà été lu. Une expiration de l'ancien Monitor d'une partie arrêtée ne
demande rien.

## 4. Coupures

Quand la mémoire manque, Claude Code tue les tâches d'arrière-plan pendant que la session
attend. C'est arrivé deux fois dans la première séance réelle. Ce n'est pas un bug à corriger.

**En mode A**, l'outil tourne dans sa propre fenêtre et Claude Code ne peut pas le couper.
Seul le Monitor peut tomber : réarme-le avec `tail -n 0 -f` sans rien demander. Si la fenêtre
elle-même s'est fermée (`live\status.json` ne bouge plus), voici ce qui est gardé :
- l'audio jusqu'à la coupure, en tranches de 5 minutes ;
- la transcription déjà écrite.

Propose alors une relance dans un nouveau dossier, en mode A ou en mode B selon la mémoire
libre.

- **Ne relance pas de toi-même.** Préviens l'utilisateur tout de suite (texte + `PushNotification`) :
  ce qui est conservé, à partir de quand plus rien n'est capté, et trois options :
  « relance » (enregistrement seul, léger), « relance tout », « stop ».
- À la relance : nouveau fichier `-partieN` (le preflight donne le nom), vérifier la mémoire
  d'abord. Sous ~2,5 Go libres, `small` risque de tout faire couper ; sous 1 Go, enregistrer
  seulement. Le compte rendu final pourra toujours être refait avec un meilleur modèle.
- `base` est un dernier recours, pas un « small un peu moins précis » : testé sur le même
  passage, il invente des répétitions et déforme les phrases au point que les suggestions
  deviennent peu fiables. Avant d'y descendre, proposer de libérer de la mémoire : le
  preflight compte les processus Python, et des dizaines de serveurs MCP laissés par
  d'anciennes sessions Claude Code en sont la cause la plus probable ici. Si `base` tourne
  quand même, prévenir l'utilisateur que la qualité baisse et suggérer moins, pas plus.
- Pour une prochaine fois, l'utilisateur peut lancer Claude Code avec
  `CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP=1` ; le mentionner une fois, pas à chaque coupure.

## 5. Stop et compte rendu

À « stop », en mode A :

1. Crée le fichier `STOP` dans le dossier (`New-Item "<dossier>\STOP"`), puis arrête le
   Monitor. L'outil termine les fenêtres en attente, écrit `live\summary.json` et ferme les WAV.
2. **La passe finale.** Lance-la en arrière-plan, quand la mémoire est libre :
   ```
   "<skill>\outil\.venv\Scripts\python.exe" -X utf8 "<skill>\outil\final_pass.py" "<dossier>" --remote-speakers <n>
   ```
   Elle sépare d'abord les voix de la sortie du PC avec pyannote : « Voix 1 », « Voix 2 ». Elle
   coupe ensuite les fenêtres le long de chaque tour de parole, une seule voix par fenêtre, puis
   refait la transcription. Mesuré le 21/10 : 2 minutes pour 3 minutes d'audio, dont 1 min 35
   pour pyannote. Compte 30 à 40 minutes pour une heure.
3. **Qui est qui.** Demande à l'utilisateur, en question à options : « Voix 1 = … ? », avec des
   indices tirés du contenu. Deux voix proches peuvent être confondues par la séparation :
   dis-le.
4. Le compte rendu se rédige comme en mode B (étape 3 ci-dessous), à partir des notes et de
   `final\transcript.final.md`. Il va dans `<dossier>\final\compte-rendu.md`.

À « stop », en mode B :

1. `TaskStop` sur l'enregistrement, la transcription et le Monitor de la partie courante.
2. `bash scripts/verifier.sh` : durée réelle de chaque partie. `ffprobe` dit « N/A » sur ces
   fichiers, c'est normal ; seul le décodage complet fait foi.
3. Rédiger le compte rendu d'après `references/compte-rendu.md`, à côté des enregistrements
   (`<prefixe>-compte-rendu.md`), à partir de la fiche tenue pendant la réunion et des
   fichiers `.live.txt`. Signaler honnêtement les trous (coupures, passages inaudibles,
   intervenants non identifiés, noms approximatifs).
4. Proposer — sans lancer — une retranscription complète avec `medium` si des noms ou des
   responsables restent douteux (~20 min pour 2 h d'audio, à faire quand la RAM est libre) :
   `"<python du venv>" scripts/live.py "<partie>.mka" medium`.
   Si le projet a un dossier privé pour ses comptes rendus, le compte rendu y va. Chaque phrase
   soufflée qui s'est révélée fausse se note, pour corriger la règle qui l'a laissée passer.
5. Mémoire : n'enregistrer que ce qui durera au-delà de la réunion et ne se retrouve pas
   ailleurs (une échéance structurante, un rôle confirmé, une préférence de l'utilisateur sur le
   coaching). Pas le contenu de la réunion lui-même : il est dans le compte rendu.

Si l'utilisateur demande ensuite « un message court avec mon avis », c'est un message à poster à
l'équipe : valider ce qui tient, deux points concrets au plus, finir par une offre de travail.

## Consentement

Enregistrer une réunion suppose que les participants le savent. Le rappeler une fois, en une
ligne, au démarrage si rien n'indique qu'ils sont prévenus — jamais plus.
