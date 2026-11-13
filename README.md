# reunion-live

**Un copilote de réunion pour Claude Code, 100 % local.** Il enregistre la réunion, la
transcrit en temps réel sur CPU, la suit au fil de l'eau et souffle des répliques courtes,
adaptées au contexte du projet et à la mémoire de la session. À la fin, il rédige le
compte rendu : décisions, actions avec responsables, dates, et ce qui vous concerne.

Né d'une séance réelle de 2 h 12 (point d'équipe, 1er octobre 2026), puis durci à partir
de tout ce qui y a cassé.

```
micro ──ffmpeg──> partie.mka ──live.py (45 s)──> partie.live.txt ──Monitor──> Claude ──> répliques
                                    │                                                         │
                                    └───────────── « stop » : vérification + compte rendu ────┘
```

## Ce qui le distingue

- **Local de bout en bout.** ffmpeg capture l'audio, faster-whisper (int8, CPU) transcrit.
  Aucun audio ni texte ne quitte la machine.
- **Robuste aux coupures.** Matroska et FLAC laissent un fichier lisible même si le
  processus est tué. Chaque relance écrit une nouvelle partie, rien n'est jamais écrasé.
  `verifier.sh` mesure la durée réelle par décodage complet (`ffprobe` renvoie « N/A » sur
  ces fichiers).
- **Une transcription nettoyée.** Il retire les répétitions que Whisper produit sur
  plusieurs segments (« Ça va? Ça va? Ça va? ») ou dans un même segment (« Teste Teste
  Teste… »), les boucles sur un son faible (« Et. Et. Et. ») et les caractères d'alphabets
  inventés. Les vraies répétitions sont conservées (« très très vite »). Les tests portent
  sur des lignes réelles.
- **Une capture mesurée, pas supposée.** Un texte connu, lu par la synthèse vocale de
  Windows, a servi à mesurer chaque source : 86 % de mots justes au micro seul, 83 % une
  fois mélangé au « Mixage stéréo », et 0 % pour le « Mixage stéréo » seul, car le son
  sortait par les écrans et non par la carte Realtek. Le skill enregistre donc le micro
  seul et explique quand réintroduire le « Mixage stéréo ».
- **Un coaching discipliné, pas bavard.** Au plus deux interventions de fond par réunion.
  Une réponse prête quand on vous nomme. Rien n'est soufflé (numéro de ticket, cause,
  capacité du produit) sans l'avoir lu dans la session. Une correction immédiate si une
  vérification contredit une réplique déjà donnée. Voir
  [`references/coaching.md`](references/coaching.md).
- **Conscient de la mémoire de la machine.** Le preflight choisit le modèle selon la RAM
  libre (`small`, `base` en dernier recours, ou enregistrement seul). Il signale aussi les
  processus orphelins qui consomment la mémoire.

## Prérequis

| Composant | Rôle |
|---|---|
| [Claude Code](https://claude.com/claude-code) | outils Bash en arrière-plan, Monitor, TaskStop, PushNotification |
| Windows + ffmpeg (DirectShow) | capture du micro |
| Python 3.12 + `faster-whisper` | transcription (venv, modèles `small` ou `base` en cache) |
| Git Bash | scripts `preflight.sh` et `verifier.sh` |

Les voix des autres participants sont captées par le micro, qui entend vos haut-parleurs.
Le « Mixage stéréo » ne sert que si votre sortie audio passe par la carte qui le fournit :
vérifiez qu'il capte un son joué avant de l'ajouter (voir `SKILL.md`). Le mode A fait mieux : il lit
la vraie sortie du PC en boucle WASAPI, sans passer par le micro.

## Installation

```bash
git clone git@github.com:jdfyras/reunion-live-partage.git ~/.claude/skills/reunion-live
```

Puis installez l'outil une fois, dans `outil/` (venv Python 3.12, dépendances, modèles) :
suivez [`outil/README.md`](outil/README.md). Les deux modes utilisent ce même venv, et aucun
chemin n'est à modifier : le skill et ses scripts partent du dossier où il est cloné.
Claude Code découvre le skill tout seul.

### Deux modes

- **Mode A, par défaut** : deux pistes (votre micro et la sortie du PC en boucle WASAPI), Cohere
  Transcribe Arabic pour la darja, le français et l'anglais, une page en direct, puis une passe
  finale qui sépare les voix. Environ 7 Go de mémoire.
- **Mode B, de secours** : micro seul et faster-whisper, décrit ci-dessus. Pour une machine
  qui manque de mémoire, ou une réunion entièrement en français.

## Utilisation

Dites-le simplement à Claude Code :

| Vous écrivez | Il fait |
|---|---|
| « j'ai une réunion dans 2 min » | preflight, enregistrement, transcription, suivi |
| `?` | résumé des dernières minutes et ce que vous pourriez dire |
| « réponds à X » | une réplique courte, prête à dire |
| « relance » | reprise après une coupure, dans une nouvelle partie |
| `stop` | arrêt, vérification des parties, compte rendu |

Le compte rendu suit le gabarit [`references/compte-rendu.md`](references/compte-rendu.md).

## Structure

```
SKILL.md                    déroulé complet, lu par Claude Code
scripts/live.py             transcription incrémentale + filtre nettoyer()
scripts/preflight.sh        périphériques, RAM, modèle conseillé, prochaine partie
scripts/verifier.sh         durée réelle de chaque partie enregistrée
references/coaching.md      règles de coaching issues de la séance réelle
references/compte-rendu.md  gabarit du compte rendu
tests/test_nettoyer.py      tests du filtre (sans dépendance)
outil/                      mode A : reunion_live.py, final_pass.py, start-meeting.ps1,
                            preflight.ps1, backup-mic.ps1, tick.sh, requirements.txt
```

## Tests

```bash
python -X utf8 tests/test_nettoyer.py
```

Le filtre a été vérifié dans les deux sens : les tests passent, et ils échouent si l'on
retire la déduplication.

## Limites connues

- **Latence d'environ 1 minute** entre la parole et la suggestion (blocs de 45 s plus le
  temps de transcription). C'est un copilote, pas un sous-titrage.
- **Les voix distantes passent par l'air** (micro qui entend les haut-parleurs) : la
  qualité dépend du volume et de la pièce. Un casque améliore votre voix mais coupe les
  autres du micro.
- **Pas d'identification des intervenants.** Quand un « toi » peut vous viser, la réplique
  le dit au conditionnel.
- **`base` dégrade fortement la qualité.** Libérer de la RAM vaut mieux que descendre de
  modèle.
- **Claude Code peut tuer les tâches d'arrière-plan** quand la mémoire manque. Pour
  l'éviter : `CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP=1`.
- **Windows uniquement** pour la capture (DirectShow). Sous macOS et Linux, il faut
  remplacer `-f dshow` par `avfoundation` ou `pulse`.

## Consentement

Enregistrer une réunion suppose que les participants le savent. Le skill le rappelle une
fois au démarrage. Les fichiers audio et les transcriptions sont exclus du dépôt
(`.gitignore`).
