# Calames HTML — Interface publique de remplacement

## Présentation du projet

Ce projet vise à créer une interface web publique pour remplacer l'interface actuelle de Calames (catalogue des archives et manuscrits des bibliothèques de l'enseignement supérieur français).

Il s'agit d'une interface web de **recherche et de navigation** dans des fonds d'archives décrits en EAD.

**Priorité absolue : reproduire les fonctionnalités de base de Calames avant d'explorer des fonctionnalités innovantes.**

## Stack technique

| Couche | Outil |
|---|---|
| Parsing XML + backend API | Python + FastAPI |
| Index de recherche | Elasticsearch |
| Frontend | Vue.js |

### Structure du projet (cible)

```
website4calamesData/
├── data/test/         # Corpus de test : fichiers EAD ad hoc + liaisons.tsv
├── backend/
│   ├── harvester/     # Moissonnage OAI-PMH de Calames
│   ├── indexer/       # Pipeline de parsing EAD → Elasticsearch
│   └── api/           # API FastAPI
└── frontend/          # Application Vue.js
```

## Données

- **Corpus Calames** : moissonné depuis l'entrepôt OAI-PMH de Calames (environ 4 000 notices), avec `liaisons.tsv` et les organismes responsables ; non versionné, son dossier est indiqué dans `corpora.json`.
- **Corpus de test** (`data/test/`) : fichiers EAD construits par Claude pour tester une règle précise ; chacun commence par un commentaire « Teste : … » qui décrit ce qu'il teste et l'attendu (affiché dans l'interface avec `?corpus=test`).

## La recherche

### Référence normative

Le guide de bonnes pratiques EAD pour les bibliothèques françaises fait référence : https://www.ead-bibliotheque.fr/guide/
Il définit les règles d'encodage à respecter (champs obligatoires, recommandés, déconseillés), compatibles avec Calames, TapIR et PiXML.

### Structure hiérarchique et héritage

Un fichier EAD est une structure de données **hiérarchique**. Certains champs sont hérités des niveaux supérieurs vers les niveaux inférieurs. La règle d'héritage est : **un champ hérité s'applique à un composant enfant sauf si ce composant déclare lui-même ce champ** (héritage par le plus proche ancêtre).

Champs héritables connus :

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
| Noms de familles | `<famname>` | Cumulatif |
| Titres d'œuvres | `<title>` (controlaccess) | Cumulatif |
| Fonctions | `<function>` | Cumulatif |
| Provenance | noms au `@role="390"` (propriétaire précédent) | Cumulatif |

Les valeurs propres d'un composant comptent plus, en recherche, que celles qu'il hérite.

La recherche doit tenir compte de ces héritages : un composant peut être trouvé via un champ hérité de son ancêtre.

### Liaisons entre fichiers

Certaines bibliothèques ont des inventaires découpés en plusieurs fichiers EAD, que Calames réorganise par relations d'**inclusion** (un fichier rattaché sous la racine d'un fichier maître, à un rang donné) et de **succession** (un fichier qui en continue un autre : une chaîne de succession forme un seul fonds, les composants des fichiers suivants s'ajoutant à ceux du premier). Ces relations sont décrites dans `liaisons.tsv` (https://calames.abes.fr/prod/lstfiles.aspx?chemin=CalamesData%5Csvdata%5C&filtre=liaisons.tsv). Les fichiers liés forment une seule hiérarchie : l'héritage, la navigation et le regroupement les traversent. Détails dans `INDEXING.md`.

### Regroupement par parent

Quand une recherche trouve assez d'enfants d'un même parent, elle renvoie le **parent** plutôt que les enfants individuellement (en indiquant combien de composants il regroupe). Deux règles, appliquées de bas en haut sur l'ensemble des résultats :

- **couverture** (par défaut) : au moins 75 % des enfants du parent sont trouvés (ou eux-mêmes regroupés) ;
- **règle des N frères** (option `sibling_grouping`) : au moins N = 3 enfants trouvés.

### Champs de recherche

- Tout le texte du composant, pondéré (titre et cote d'abord ; détail dans `INDEXING.md`)
- Titre (`<unittitle>`)
- Cote, actuelle ou ancienne (`<unitid>`), sous n'importe quelle forme (« Ms 1234 » = « ms1234 »)
- Date (`<unitdate>`) : texte et période
- Personnes avec leur rôle (`<persname role="...">`, `<corpname>`, `<famname>`, `<origination>`)
- Type de document (`<genreform>` par `@type`, `<physfacet>`)
- Sujets, lieux, titres d'œuvres, fonctions (`<subject>`, `<geogname>`, `<title>`, `<function>`)
- Provenance (propriétaire précédent), langue, institution, présence d'une version numérique
- Syntaxe de Calames : `OR` / `|`, `-exclu`, `+requis`, `^début`, `"expression"`

## La navigation

- **Fil d'Ariane** de l'ancêtre de plus haut niveau (fichier maître compris) au composant ; **frères** parcourus par un curseur ; **arbre** du fonds.
- **Dépliage des descriptions** des enfants depuis le parent, selon ce qui reste lisible : un enfant à la fois toujours ; tous les enfants directs jusqu'à 50 ; tout le sous-arbre jusqu'à 200 composants. Au-delà, la raison est affichée.
- **XML EAD natif** à chaque niveau (sans les composants enfants par défaut).
- **Description complète** sous les libellés de Calames (rubriques EAD, rôles, organisme responsable, anciennes cotes, versions numériques) ; la cote est toujours affichée avant le titre.
- **Résultats** : « Retour aux résultats » ramène à la liste (pas à la page précédente) ; résultat précédent / suivant.
- **Adresses Calames** (`/pub/ms/<id>`) redirigées vers les pages correspondantes, pour garder les liens existants.
