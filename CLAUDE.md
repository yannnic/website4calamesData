# Calames HTML — Interface publique de remplacement

## Présentation du projet

Ce projet vise à créer une interface web publique pour remplacer l'interface actuelle de Calames (catalogue des archives et manuscrits des bibliothèques de l'enseignement supérieur français).

Il s'agit d'une interface web de **recherche et de navigation** dans des fonds d'archives décrits en EAD.

**Priorité absolue : reproduire les fonctionnalités de base de Calames avant d'explorer des fonctionnalités innovantes.**

## Stack technique

| Couche | Outil |
|---|---|
| Parsing XML + backend API | Python + FastAPI |
| Index de recherche | MeiliSearch |
| Frontend | Vue.js |

### Structure du projet (cible)

```
calames-html/
├── data/              # Fichiers EAD d'exemple
├── backend/
│   ├── indexer/       # Pipeline de parsing EAD → MeiliSearch
│   └── api/           # API FastAPI
└── frontend/          # Application Vue.js
```

## Données

Les fichiers EAD d'exemple se trouvent dans `./data/`. Ils ont été générés par Claude à titre d'illustration et pourront évoluer au fil du développement des fonctionnalités.

## La recherche

### Référence normative

Le guide de bonnes pratiques EAD pour les bibliothèques françaises fait référence : https://www.ead-bibliotheque.fr/guide/
Il définit les règles d'encodage à respecter (champs obligatoires, recommandés, déconseillés), compatibles avec Calames, TapIR et PiXML.

### Structure hiérarchique et héritage

Un fichier EAD est une structure de données **hiérarchique**. Certains champs sont hérités des niveaux supérieurs vers les niveaux inférieurs. La règle d'héritage est : **un champ hérité s'applique à un composant enfant sauf si ce composant déclare lui-même ce champ** (héritage par le plus proche ancêtre).

Champs héritables connus :

| Champ | Balise EAD | Règle |
|---|---|---|
**Héritage simple** (le plus proche ancêtre ayant une valeur remplace le vide) :

| Champ | Balise EAD | Règle |
|---|---|---|
| Langue | `<langmaterial><language>` | Héritable, sauf si langue déclarée au niveau inférieur |
| Date | `<unitdate>` | Héritable (bloc complet : affichage, normal, début, fin), sauf si date déclarée au niveau inférieur |
| Conditions d'accès | `<accessrestrict>` | Héritable vers tous les descendants |
| Conditions d'utilisation | `<userestrict>` | Héritable vers tous les descendants |
| Organisme responsable | `<repository>` | Héritable (généralement stable sur tout le fonds) |

**Héritage cumulatif** (les valeurs s'accumulent de niveau en niveau, sans doublon) :

| Champ | Balise EAD | Règle |
|---|---|---|
| Sujets | `<subject>` | Cumulatif : les sujets des ancêtres s'ajoutent aux sujets propres |
| Noms géographiques | `<geogname>` | Cumulatif |
| Genres/formes | `<genreform>` | Cumulatif |
| Noms de collectivités | `<corpname>` (controlaccess) | Cumulatif |
| Noms de personnes | `<persname>` (controlaccess) | Cumulatif |

La recherche doit tenir compte de ces héritages : un composant peut être trouvé via un champ hérité de son ancêtre.

### Regroupement par parent (règle des N frères)

Si une recherche renvoie au moins **N éléments frères** (composants de même niveau partageant le même parent), alors il faut renvoyer le **parent** plutôt que les enfants individuellement. La valeur de N est à définir.

### Champs de recherche

- Titre (`<unittitle>`)
- Date (`<unitdate>`)
- Personnes avec leur rôle (`<persname role="...">`, `<corpname>`, `<origination>`)
- Type de document (`<genreform>`, `<physfacet>`)
- Sujets (`<subject>`, `<geogname>`)
- À compléter selon les besoins

## La navigation

[ à compléter ]
