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
| `parent_id` | `@xml:id` du composant parent | `null` pour la racine |
| `ancestor_ids` | Liste ordonnée racine → parent direct | Utilisé pour navigation et héritage |
| `depth` | Profondeur dans l'arbre | `0` = archdesc (fonds), `1` = enfants directs… |
| `position` | Rang parmi les frères | Ordre de tri dans la navigation |

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

## Ce qui n'est pas implémenté (par rapport à SQL)

| Fonctionnalité SQL | État | Notes |
|---|---|---|
| Accumulation du plein texte des descendants dans les ancêtres (`DocumentIndexFullText`) | **Absent** | Écart majeur : un fonds n'est pas interrogeable sur du texte présent uniquement au niveau pièce |
| `famname` distinct de `persname` | **Absent** | Les noms de famille sont fondus dans `pers_names` |
| `EntreeSecondaire` (second terme qualificatif dans un `<controlaccess>`) | **Absent** | Logique catalogaphique ISAD/UNIMARC |
| `genreform[@type="type_de_document"]` et `[@type="technique"]` séparés | **Absent** | Tous les `<genreform>` sont dans `genre_forms` sans distinction de `@type` |
| `DocumentIndexDao` (présence de liens DAO) | **Absent** | |
| `DocumentIndexHistoire` (notes historiques indexées séparément) | **Absent** | Contenu indexé dans le plein texte global Elasticsearch |
| PPN sur les sujets (`<subject @authfilenumber>`) | **Absent** | Uniquement sur `<persname>` pour l'instant |

---

## Regroupement par parent (`sibling_grouping`)

Si une recherche renvoie ≥ `SIBLING_THRESHOLD` composants frères (même parent), ils sont remplacés
par leur parent dans les résultats (récursif). Valeur par défaut : `3`.

Désactivé par défaut dans l'API ; à activer via le paramètre `sibling_grouping=true`.

---

## Compatibilité EAD

Le parser gère :
- EAD 2002 avec namespace (`urn:isbn:1-931666-22-9`) ou sans namespace
- `<c>` directs ou encapsulés dans un ou plusieurs `<dsc>`
- `@id` ou `@xml:id` sur les composants (repli sur identifiant auto-généré `auto-{n}`)
- Niveaux EAD variés : `fonds`, `recordgrp`, `series`, `subseries`, `file`, `item`…
