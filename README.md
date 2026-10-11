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
