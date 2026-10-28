# Calames HTML — Spécifications de l'indexation

Ce document décrit le modèle de données produit par le parser EAD Python et indexé dans Elasticsearch.
Il est à lire en regard de `sql_procedures_legacy/INDEXES.md` qui documente l'implémentation SQL Server d'origine.

---

## Architecture générale

Chaque fichier EAD est parsé en une liste de **composants** (`Component`), un par nœud de l'arbre
(`<archdesc>` + tous les `<c>`). Chaque composant est un document plat poussé dans Elasticsearch.

L'héritage et l'accumulation des champs sont résolus **à l'indexation**, pas à la requête.

---

## Identifiants

| Champ | Source EAD | Notes |
|---|---|---|
| `node_id` | `{ead_id}#{xml:id}` | Identifiant Elasticsearch (`_id`). Si `@xml:id` absent, génère `auto-{n}` |
| `ead_id` | `//eadheader/eadid` | Identifiant de l'instrument de recherche |
| `parent_id` | `@xml:id` du composant parent | `null` pour la racine ; pour la racine d'un fichier rattaché, la racine du fichier parent |
| `ancestor_ids` | Liste ordonnée racine → parent direct | Utilisé pour navigation et héritage. Traverse les fichiers liés |
| `depth` | Profondeur dans l'arbre | `0` = archdesc d'un fichier de premier niveau, `1` = enfants directs… |
| `position` | Rang parmi les frères | Ordre de tri dans la navigation |
| `children_count` | Nombre d'enfants directs | Fichiers rattachés compris |
| `parent_children_count` | Nombre d'enfants du parent | `0` pour la racine. Sert au calcul de couverture du regroupement |
| `file_root` | `true` pour l'archdesc du fichier | Racine d'un fichier, rattaché ou non |
| `ead_ids` | `ead_id` du fichier et des fichiers qui le contiennent | Filtre `ead_id` de `/search` : un fichier maître couvre ses fichiers rattachés |

---

## Champs descriptifs

| Champ | Source EAD | Notes |
|---|---|---|
| `level` | `@level` ou `@otherlevel` | `fonds`, `series`, `subseries`, `file`, `item`… |
| `unitid` | `//did/unitid` | Cote |
| `title` | `//did/unittitle` | Texte complet (inclut sous-éléments) |
| `date_display` | `//did/unitdate` (texte) | Forme affichable |
| `date_normal` | `//did/unitdate/@normal` | Plage ISO : `"1952/2018"` |
| `date_start` | 4 premiers caractères avant `/` | Année de début (int) |
| `date_end` | 4 premiers caractères après `/` | Année de fin (int) |
| `abstract` | `//did/abstract` | Présentation sommaire |
| `scope_content` | `//scopecontent` | Description du contenu (hors `<head>`) |
| `biography` | `//bioghist` | Notice biographique/historique |
| `extents` | `//did/physdesc/extent` | Métrage, nombre d'unités |
| `phys_facets` | `//did/physdesc/physfacet` | Facettes physiques |
| `access_restrict` | `//accessrestrict` | Conditions d'accès |
| `use_restrict` | `//userestrict` | Conditions d'utilisation |

---

## Agents

### Créateurs (`creators`)

Source EAD : `//did/origination/persname` et `//did/origination/corpname`

Liste de dicts : `[{"name": …, "role": …, "type": "person"|"corp"}]`

- `name` : forme normale (`@normal`) si disponible, sinon texte brut
- `role` : `@role` (code UNIMARC ou libellé)
- `type` : `"person"` ou `"corp"`

### Autorités (sujets et agents indexés)

| Champ | Balises collectées | Usage |
|---|---|---|
| `subjects` | `<subject>` | Plein texte (normal + littéral) |
| `subjects_norm` | `<subject/@normal>` | Facette / filtre |
| `geo_names` | `<geogname>` | Plein texte |
| `geo_names_norm` | `<geogname/@normal>` | Facette / filtre |
| `genre_forms` | `<genreform>` | Plein texte (tous `@type`) |
| `genre_forms_norm` | `<genreform/@normal>` | Facette / filtre |
| `corp_names` | `<corpname>` | Plein texte |
| `corp_names_norm` | `<corpname/@normal>` | Facette / filtre |
| `fam_names` | `<famname>` | Plein texte |
| `fam_names_norm` | `<famname/@normal>` | Facette / filtre |
| `pers_names` | `<persname>` | Plein texte (forme normale préférée) |
| `pers_name_roles` | `<persname>` | `"NomNormal::role"` — liens par rôle |
| `pers_name_ids` | `<persname[@source="Sudoc"]>` | `"NomNormal\|\|authfilenumber"` — liens IdRef |

**Périmètre de collecte** : ces balises sont collectées dans **tout le scope du composant**
(pas seulement dans `<controlaccess>`), sauf dans les éléments enfants (`<c>`, `<dsc>`) et dans
`<origination>`. Cela inclut donc les mentions inline dans `<scopecontent>`, `<bioghist>`, etc.
C'est un choix délibéré pour maximiser le rappel en recherche, au prix d'un léger bruit potentiel.
SQL cible explicitement `//controlaccess/*`.

**Note** : les `<persname>` et `<corpname>` de `<origination>` (créateurs du fonds) sont traités
séparément et vont dans le champ `creators`, pas dans `pers_names`.

---

## Dépôt conservateur

| Champ | Source EAD | Notes |
|---|---|---|
| `repository` | `//did/repository/corpname` (texte) | Nom de l'institution |
| `repository_id` | `//did/repository/corpname/@authfilenumber` | PPN Sudoc de l'institution |

---

## Langues

| Champ | Source EAD |
|---|---|
| `languages` | `//did/langmaterial/language/@langcode` (liste de codes ISO) |

---

## Règles d'héritage

L'héritage est résolu à l'indexation, par parcours de l'arbre. Il existe deux modes :

### Héritage simple

Si un champ est absent d'un composant, il est rempli par la valeur du **plus proche ancêtre** qui le
possède. Le composant qui déclare sa propre valeur n'est pas écrasé.

| Champ | Règle |
|---|---|
| `access_restrict` | Plus proche ancêtre |
| `use_restrict` | Plus proche ancêtre |
| `languages` | Plus proche ancêtre |
| `repository` | Plus proche ancêtre |
| `repository_id` | Plus proche ancêtre |
| `date_display`, `date_normal`, `date_start`, `date_end` | Groupe : les quatre champs sont hérités ensemble depuis le plus proche ancêtre qui a une `date_normal` |

### Héritage cumulatif

Un composant **conserve ses propres valeurs** et reçoit en plus les valeurs de tous ses ancêtres
(sans doublon). Les valeurs propres apparaissent en premier, puis les valeurs du parent le plus
proche, puis celles des ancêtres plus lointains.

| Champ | Règle |
|---|---|
| `subjects`, `subjects_norm` | Cumulatif |
| `geo_names`, `geo_names_norm` | Cumulatif |
| `genre_forms`, `genre_forms_norm` | Cumulatif |
| `corp_names`, `corp_names_norm` | Cumulatif |
| `pers_names`, `pers_name_roles`, `pers_name_ids` | Cumulatif |

**Différence avec SQL** : dans l'implémentation SQL (procédures `H`/`HC`), la propagation est
top-down (parent → enfants). Notre implémentation est équivalente pour le résultat final.

### Remontée des dates (bottom-up)

Après le parsing, un second parcours **post-ordre** remonte les dates des feuilles vers les
ancêtres qui n'en ont pas. Pour chaque composant sans `date_normal`, on calcule :

- `date_start` = minimum de tous les `date_start` des enfants (récursivement déjà résolus)
- `date_end`   = maximum de tous les `date_end` des enfants

Ce parcours s'exécute **avant** l'héritage top-down, de sorte que les dates remontées
bénéficient ensuite normalement à leurs descendants sans date.

**Exemple :**

```
Avant résolution :
  Fonds A          date: —
  ├── Série B      date: —
  │   ├── Dossier C    date: 1950/1960
  │   └── Dossier D    date: 1970/1985
  └── Série E      date: 1920/1930

Après bottom-up :
  Fonds A          date: 1920/1985  ← min(1920,1950) / max(1930,1985)
  ├── Série B      date: 1950/1985  ← min(1950,1970) / max(1960,1985)
  │   ├── Dossier C    date: 1950/1960  (inchangé)
  │   └── Dossier D    date: 1970/1985  (inchangé)
  └── Série E      date: 1920/1930  (inchangé — avait sa propre date)
```

**Différence avec SQL** : `sp_DocumentIndexDate` retient `Cgm_DateLast` (la date la plus récente
du sous-arbre). Notre implémentation retient la **plage complète** min/max, plus utile pour
représenter la couverture chronologique réelle d'un fonds.

---

## Liaisons entre fichiers (`liaisons.tsv`)

Les inventaires volumineux sont découpés en plusieurs fichiers EAD que Calames réassemble en
une seule hiérarchie, d'après [`liaisons.tsv`](https://calames.abes.fr/prod/lstfiles.aspx?chemin=CalamesData%5Csvdata%5C&filtre=liaisons.tsv)
(`backend/indexer/liaisons.py`). Une ligne par fichier, sans en-tête, séparateur tabulation :

| Colonne | Contenu |
|---|---|
| 1 | FileId du fichier |
| 2 | Libellé |
| 3 | Chemin d'administration (`admin;RCR;…`) |
| 4 | Indicateur (non utilisé) |
| 5 | FileId du fichier **précédent** (succession), `0` sinon |
| 6 | FileId du fichier **parent** (inclusion), `0` sinon |
| 7 | Rang parmi les fichiers inclus dans le parent |

- **Inclusion** : la racine du fichier devient un enfant de la racine du fichier parent, après
  les composants propres de celle-ci, dans l'ordre des rangs (puis du libellé).
- **Succession** : le fichier est placé juste après le précédent, sous le même parent.
- Un fichier est relié à sa ligne par le FileId de son `<eadid>` : `@identifier` ou texte
  (`…_CALAMESFileId-4752`), à défaut `@url` (`…/FileId-4752`). Dans une chaîne de succession,
  `@url` donne souvent le FileId du premier fichier : un fichier connu par `@url` seulement dont
  le FileId est détenu par un autre fichier est placé juste après celui-ci.
- Un fichier dont le parent est absent du corpus est rattaché au plus proche ancêtre présent,
  à la place du parent manquant. Sans ligne dans `liaisons.tsv`, un fichier reste autonome.

Tout se résout à l'indexation : profondeur, ancêtres, titres d'ancêtres, compteurs et
**héritage** (simple et cumulatif) traversent les fichiers comme s'il n'y en avait qu'un. Le fil
d'Ariane, l'arbre de navigation et le regroupement hiérarchique fonctionnent donc sans
traitement particulier. Les dates ne remontent pas d'un fichier rattaché vers son parent.

Le fichier est cherché dans le dossier EAD (`EAD_DIR/liaisons.tsv`, option `--liaisons` de
l'indexeur, variable `LIAISONS_FILE` du watcher). Le moissonneur le télécharge à chaque passe
(`python harvester/harvester.py --liaisons-only` pour ne télécharger que lui).

Indexation complète : les parents sont indexés avant leurs fichiers rattachés. Watcher : un
fichier réindexé entraîne ses fichiers rattachés (ils en héritent). Après un ajout, une
suppression ou une modification de `liaisons.tsv`, les fichiers qui changent de parent sont
réindexés, et les compteurs et positions des parents concernés sont mis à jour.

---

## Plein texte : comparaison avec Calames

Dans Calames, `sp_DocumentIndexFullText` remplit une colonne texte unique par composant
(`DocumentIndexFullText.fulltext`), par une CTE récursive **descendante** (`a.parent = b.id` :
l'enfant reçoit les valeurs de son parent). Elle concatène, puis nettoie (`dbo.T()`) :

| Partie | Contenu | Le long de l'arbre |
|---|---|---|
| `titre` | Tout le texte (`//text()`) du composant lui-même : did, scopecontent, bioghist, custodhist, acqinfo, notes… (archdesc sans `<dsc>` ; `<c>` sans ses enfants, via `dbo.Hg()`) | **Non cumulé** |
| `controlaccess` | Texte et `@normal` des `persname`, `corpname`, `geogname`, `famname`, `subject`, `title` | **Cumulé vers le bas** (ancêtres + propres) |
| `date` | `data(//unitdate)` | **Cumulé vers le bas** (toutes les dates des ancêtres) |
| `ppnaccess` | `@authfilenumber` des autorités `@source="Sudoc"` (filtrés par `dbo.GetRejete()`) | **Cumulé vers le bas** |

Conséquences : une pièce est trouvée par les autorités et les dates de ses ancêtres ; un fonds
**n'est pas** trouvé par le texte de ses pièces (contrairement à ce qu'indique
`sql_procedures_legacy/INDEXES.md`, la CTE n'accumule pas vers le haut).

Non visibles dans le dump SQL : les fonctions `dbo.T()`, `dbo.Hg()`, `dbo.GetRejete()`, et
l'interrogation (aucun `CONTAINS`/`FREETEXT`, ni définition du catalogue plein texte : analyseur,
langue, mots vides).

| | Calames (SQL) | Elasticsearch (ici) |
|---|---|---|
| Texte propre du composant | Tout son XML, à plat | Tout son texte, en champs pondérés (ci-dessous) |
| Autorités des ancêtres | Cumulées, même poids que les propres | Cumulées, mais avec un poids faible : les propres d'abord |
| Titres des ancêtres | Non | Complètent une requête, sans la satisfaire seuls |
| Dates des ancêtres | Toutes, en texte | La plus proche : en texte (poids faible) et en champs numériques (filtres de période) |
| Texte des descendants dans le parent | Non | Non ; le regroupement hiérarchique fait remonter le parent quand assez d'enfants sont trouvés |

### Construction du plein texte

Champs cherchés par `q` (`SEARCH_FIELDS`, `backend/api/filters.py`), du plus fort au plus faible :

| Poids | Champs | Contenu |
|---|---|---|
| ×4, ×3 | `title`, `unitid`, `creator_names` | Titre, cote, producteurs (`<origination>`) |
| ×2 | `pers_names_own`, `corp_names_own`, `fam_names_own`, `subjects_own`, `geo_names_own`, `genre_forms_own` | Autorités **propres** du composant |
| ×1,5 à ×1 | `abstract`, `scope_content`, `biography`, `phys_facets` | Résumé, présentation du contenu, biographie, description physique |
| ×0,5 | `other_text` | Tout autre texte descriptif : `custodhist`, `acqinfo`, `arrangement`, `appraisal`, `accruals`, `processinfo`, `phystech`, `altformavail`, `originalsloc`, `relatedmaterial`, `separatedmaterial`, `otherfindaid`, `bibliography`, `fileplan`, `odd`, `note`, `prefercite`, et dans `<did>` : `note`, `materialspec`, `physloc` (sans les `<head>`) |
| ×0,5 | `date_display` | Date en texte (« 1914 » trouve « 1914-1918 ») |
| ×0,3 | `pers_names`, `corp_names`… | Autorités propres **et héritées** : une valeur héritée n'atteint que ce poids |
| ×0,3 | `ancestor_titles` | Titres des ancêtres |

Règles de la requête :

- tous les mots doivent être trouvés (ET), éventuellement dans des champs différents ; tolérance
  aux fautes de frappe (1 à partir de 7 lettres, 2 à partir de 11) ;
- au moins un mot doit être trouvé **hors** des titres des ancêtres : « lettre quillebeuf » trouve
  la lettre d'un fonds Quillebeuf, mais « quillebeuf » seul ne renvoie pas toutes ses pièces ;
- `"expression entre guillemets"` : ces mots, dans cet ordre, dans un même champ, sans
  racinisation ni mots vides (sous-champs `.exact`, analyseur `fr_exact`) ;
- bonus quand la requête figure telle quelle dans le titre ou une autorité propre (`.exact`) ;
- une cote sous n'importe quelle forme : « Ms 1234 », « MS.1234 » et « ms1234 » se valent
  (`unitid.cote`, analyseur `cote` : suites de lettres ou de chiffres).

Les filtres par facette et les recherches par champ (`subject=…`, `pers_name=…`) portent toujours
sur l'union propre + héritée : l'héritage reste exact pour eux.

## Ce qui n'est pas implémenté (par rapport à SQL)

| Fonctionnalité SQL | État | Notes |
|---|---|---|
| Texte des dates de **tous** les ancêtres dans le plein texte | **Différent** | Date du plus proche ancêtre daté, en texte et filtrable par période |
| `EntreeSecondaire` (second terme qualificatif dans un `<controlaccess>`) | **Absent** | Logique catalogaphique ISAD/UNIMARC |
| `DocumentIndexDao` (présence de liens DAO) | **Absent** | |
| `DocumentIndexHistoire` (provenance : rôles 390, `acqinfo`, `custodhist`, `note[@type="provenance"]`) | **Partiel** | Pas d'index dédié ; le texte est cherché dans `other_text` |
| PPN sur les sujets (`<subject @authfilenumber>`) | **Absent** | Uniquement sur `<persname>` pour l'instant |

---

## Regroupement hiérarchique

Avec une requête texte et sans filtre `level`, les résultats sont regroupés par Elasticsearch
sur **l'ensemble** des composants trouvés (`backend/api/grouping.py`). Un parent remplace ses
descendants trouvés quand ses enfants directs trouvés (ou eux-mêmes regroupés) atteignent :

- **couverture** (par défaut) : au moins `COVERAGE_THRESHOLD` (75 %) de ses enfants ;
- **règle des N frères** (`sibling_grouping=true`) : au moins `SIBLING_THRESHOLD` (3) enfants.

La règle est appliquée de bas en haut jusqu'à stabilité. La liste contient les parents regroupés
les plus hauts et les composants trouvés hors de ces sous-arbres. Un parent regroupé prend le
score de son meilleur descendant et porte `grouped_count`, son nombre de descendants trouvés.
Le classement, le total et la pagination sont ceux d'Elasticsearch. Un composant trouvé peut
apparaître à côté de certains de ses descendants quand ceux-ci n'atteignent pas le seuil.

---

## Compatibilité EAD

Le parser gère :
- EAD 2002 avec namespace (`urn:isbn:1-931666-22-9`) ou sans namespace
- `<c>` directs ou encapsulés dans un ou plusieurs `<dsc>`
- `@id` ou `@xml:id` sur les composants (repli sur identifiant auto-généré `auto-{n}`)
- Niveaux EAD variés : `fonds`, `recordgrp`, `series`, `subseries`, `file`, `item`…
