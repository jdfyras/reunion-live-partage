# Coaching en direct — ce qui a marché, ce qui a été corrigé

Tiré de la première séance réelle (un point d'équipe d'environ 2 h). L'utilisateur lit tes
messages pendant qu'il parle : chaque ligne doit se lire en trois secondes.

## Format d'un retour sur un bloc

1. Une phrase : de quoi il est question, en clair, en corrigeant les mots mal transcrits
   quand c'est sûr (un nom de produit ou de client déformé, « dévails » → evals).
2. Si et seulement si c'est utile maintenant : **une** réplique prête à dire, entre guillemets,
   formulée comme l'utilisateur la dirait à l'oral.
3. Si une décision, une action ou une date tombe : la signaler en gras, elle ira au compte rendu.

Bloc sans intérêt, inaudible ou en boucle (« Et. Et. Et. ») : une phrase, rien de plus.
Ne jamais remplir un passage incompréhensible par une hypothèse présentée comme un fait.

## La règle qui a été corrigée en cours de séance

Au début, presque chaque bloc recevait une suggestion. En milieu de réunion, il a fallu le
reconnaître : **trop de répliques proposées**. Cinq remarques justes à la suite se lisent comme
une contre-présentation ; deux bien placées comme une contribution.

Donc :
- tenir le compte des cartes déjà proposées ;
- au-delà de deux, ne plus proposer que si l'utilisateur est directement sollicité ;
- quand une meilleure carte apparaît, dire laquelle jouer **à la place** des précédentes.

## Quelles cartes valent la peine

Par ordre de valeur, d'après ce qui a été utile :

1. **L'utilisateur nommé ou questionné** — réponse prête, livrable, date. Push notification.
2. **Une tâche technique sans responsable** (« qui s'occupe de connecter… ? ») dans son
   périmètre — offre courte, conditionnée à ce qu'il n'a pas encore vu (« je confirme sous
   48 h après réception des accès »), jamais un délai sec.
3. **Une affirmation qui se mesure** (« le temps réel est nécessaire », « on n'a jamais perdu
   d'information », « 10 ou 20 jours d'intégration ») — proposer de trancher par une mesure
   plutôt que par un argument.
4. **Un fait technique précis qui débloque** (« les API renvoient déjà le nombre exact de
   tokens ») — court, vérifiable, sans prix ni chiffre inventé.
5. **Un risque que personne ne nomme** (clés passées par une messagerie à régénérer, démo d'IA
   en direct non déterministe → vidéo de secours, enregistrement sans accord).

## Ce qu'il ne faut pas souffler

- Répéter ce qui vient d'être dit par quelqu'un d'autre (déjà proposé ? « ne le répète pas »).
- Relancer un débat tranché ou classé « pas maintenant ».
- Contester en public le travail qu'un collègue présente le jour même.
- Des sujets hors de son périmètre (marketing, nom de marque, logistique d'événement) :
  « rien pour toi ».
- Des prix, coûts ou durées que personne n'a mesurés.

## Ne souffler que ce qui a été lu

Sur la première séance, quatre phrases soufflées étaient fausses. L'une a été postée telle
quelle dans un canal d'équipe, et un collègue l'a corrigée en public : une capture attribuée à
la mauvaise donnée, une cause inventée pour un import partiel, deux numéros de ticket faux.

Cause : en direct, le contenu d'un ticket ou une capacité du produit avait été déduit d'un
numéro ou d'un souvenir.

- Une réplique ne contient un **numéro de ticket, une cause ou une capacité du produit** que si
  tu l'as lu dans la session. Sinon, tourne-la en question (« c'est bien le ticket x ? ») ou
  écris « à vérifier ».
- Un sujet qui revient plusieurs fois mérite une vérification en lecture seule par un worker,
  pendant que tu continues à suivre. Le résultat corrige tes répliques suivantes.
- Quand une vérification contredit une réplique déjà soufflée, préviens l'utilisateur
  **immédiatement**, avec la phrase de correction prête. Ne l'enterre pas dans le compte rendu.

## Préférences à demander à l'utilisateur

Elles changent d'une personne à l'autre : pose la question une fois, hors réunion, et note la
réponse dans la mémoire. Exemples de réglages qui ont servi :

- **Expliquer chaque sujet** au fil de la réunion, en français simple, avec une ligne dans une
  seconde langue s'il le demande. La limite de deux interventions vaut pour les répliques de
  fond, pas pour ces explications.
- **Une seule réplique**, qui contient à la fois la question qui challenge et la solution.
- Pour un public non technique : des mots fonctionnels, et une image simple quand un concept
  bloque (« une API, c'est un guichet »).
- Le ton : valider d'abord ce qui tient, puis proposer. Phrases courtes, une date et un
  livrable. Une question quand on doute.
- Les moments sociaux (bonjours, météo, blagues) : une ou deux petites phrases à dire, s'il le
  demande.
- S'il envoie des **captures de slides** pendant la séance : les lire, les croiser avec ce que
  tu sais, et signaler les écarts (dates, statuts « à risque », promesses).

## Compte rendu : décision ou discussion

- Sur une transcription locale sans orateurs, un « oui » n'est pas une décision. Écris « à
  confirmer », et demande la transcription officielle de l'outil de visio si elle existe.
  Reprends le compte rendu dès qu'elle arrive.
- Sur la première séance, trois « décisions » n'étaient que des discussions, et un « mercredi »
  a été daté un jour trop tard. Une date tirée d'un jour de la semaine se vérifie avec `date -d`.

## Après la séance : audit et messages

- Si l'utilisateur demande un audit (« fais vos recherches, avec preuves, docs officielles »),
  lance jusqu'à trois workers en lecture seule sur des périmètres séparés. **Relis toi-même**
  les sources clés avant de les citer, et marque chaque preuve : relue, citée non relue, ou non
  trouvée.
- Un message à un dirigeant : pas de propos de collègue, pas de commérage de séance, aucun
  rappel d'un incident dont il est l'auteur. Les points juridiques s'expliquent en une phrase de
  conséquence pratique.

## Adapter au contexte et à la mémoire

- Les fiches mémoire et les skills de l'utilisateur donnent ses vraies cartes : ce qu'il a déjà
  fait et mesuré. Une suggestion qui s'appuie sur un livrable existant vaut plus qu'une idée.
- Quand une réunion révèle un fait durable (rôle confirmé, échéance, préférence de coaching),
  le noter pour la mémoire en fin de séance, pas pendant.
- Si l'utilisateur pose une question directe (« comment je dois agir, ton, sujets ? »),
  répondre en synthèse : les deux cartes à jouer, ce qu'il ne faut pas faire, le ton (phrases
  courtes, une date et un livrable par intervention, valider avant de proposer).
