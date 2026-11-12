# FC St Léon

Appli d'équipe du FC St Léon (foot à 7) : inscription des joueurs, calendrier des séances et présences, compteur de match (2-3-1 / 3-2-1, 2 × 30 min) et résultats.

- `index.html` : l'appli complète (une seule page), publiée par GitHub Pages (https://rottweilert.github.io/fc-st-leon/) à chaque modification de ce dépôt.
- Données : base Firestore du projet Firebase `fc-st-leon` (collections `fc_*`).
- `firestore.rules` : règles d'accès à coller dans Firebase → Firestore Database → Règles.

## Moteur de statistiques et de possession

La saisie se limite à : passe (réussie / ratée), duel (gagné / perdu), tir (non cadré / cadré / but) et, pour le gardien, arrêt / but encaissé.
Tout le reste est déduit par le moteur, dans `index.html` entre `/*ENGINE-START*/` et `/*ENGINE-END*/` :

- passe ratée → perte de balle, ballon à l'adversaire ;
- duel gagné avec le ballon → dribble réussi ; sans le ballon → récupération ;
- duel perdu avec le ballon → dribble raté + perte de balle ;
- un but = 1 tir + 1 tir cadré + 1 but, ballon à l'adversaire pour l'engagement ;
- une passe ou un tir alors que l'adversaire avait le ballon → récupération non notée : la possession revient à nous, sans rien créditer à un joueur.

Les événements bruts sont gardés (sur l'appareil pendant le match, puis dans le match enregistré) : stats et possession sont recalculées en les rejouant.
Le temps de possession est mesuré en temps de jeu : les pauses et la mi-temps ne comptent pas.

Tests : `node tests/moteur.test.js` (lancés aussi automatiquement à chaque modification, action « Tests du moteur de stats »).

## Notifications push

Les visiteurs activent eux-mêmes les notifications dans l'onglet **Effectif**, carte « Sur ton téléphone » (bouton explicite, jamais de demande au chargement), choisissent leurs catégories et peuvent se désabonner à tout moment.

**Catégories** : séance modifiée ou annulée · nouvelle séance au calendrier · résultat d'un match et vote · rappel du samedi 16 h (présences non renseignées, réservé aux inscrits) · messages de l'équipe.

**Comment ça marche**

- Le site (GitHub Pages, sans serveur) obtient un jeton Firebase Cloud Messaging avec la clé Web Push du projet et l'écrit dans la collection `fc_push` : une fiche par appareil (jeton, profil, catégories). Les règles (`firestore.rules`) interdisent toute lecture de `fc_push` depuis le site.
- L'envoi est fait par l'action GitHub **Notifications** (`.github/workflows/notifications.yml` + `.github/notifications.py`), avec le compte de service Firebase rangé dans le secret `FCM_COMPTE` (jamais dans le code). Toutes les 15 minutes, elle compare le calendrier et les matchs à leur état précédent : une séance ou un résultat n'est annoncé qu'une fois ; une simple correction de match ou un ticket de l'onglet Notes n'envoie rien.
- Chaque envoi est consigné dans la collection privée `fc_push_log` et dans l'historique de l'action. Les abonnements des appareils qui ne répondent plus sont effacés automatiquement.
- Le service worker (`sw.js`, le même que pour le hors-ligne) affiche la notification et ouvre l'appli sur le bon onglet (`#calendrier`, `#resultats`…).

**Envoyer un message à la main** (réservé aux personnes qui ont le droit d'écrire dans ce dépôt : c'est GitHub qui vérifie) : GitHub → onglet *Actions* → *Notifications* → *Run workflow* → mode `message`, titre, texte, catégorie, onglet à ouvrir. Cocher *aperçu* pour voir le message et le nombre de destinataires sans rien envoyer.

**Mise en service (une seule fois)**

1. Console Firebase → projet `fc-st-leon` → *Firestore Database* → *Règles* : coller le contenu de `firestore.rules`, *Publier*.
2. Console Firebase → ⚙ *Paramètres du projet* → *Comptes de service* → *Générer une nouvelle clé privée* (fichier `.json`).
3. GitHub → dépôt → *Settings* → *Secrets and variables* → *Actions* → *New repository secret* : nom `FCM_COMPTE`, valeur = tout le contenu du fichier `.json`. Supprimer ensuite le fichier.
4. Activer les notifications sur un téléphone, puis *Actions* → *Notifications* → *Run workflow* → mode `test`.

Tant que l'étape 1 n'est pas faite, l'appli garde l'ancien rangement des jetons (champ `push` de la fiche du joueur) et bascule toute seule ensuite. Tant que l'étape 3 n'est pas faite, rien n'est envoyé.

**Limites** : iPhone et iPad seulement si l'appli est installée sur l'écran d'accueil (iOS 16.4 ou plus) ; délai jusqu'à 15 minutes (voire plus quand GitHub est chargé) pour les envois automatiques ; pas de notifications dans les navigateurs qui ne gèrent pas le Web Push.

**Tests** : `python3 tests/notifications.test.py` (faux serveur, aucun envoi réel).
