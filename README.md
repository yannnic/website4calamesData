# Calames HTML

Interface web publique de recherche et navigation dans des fonds d'archives décrits en EAD, destinée à remplacer l'interface actuelle de [Calames](https://calames.abes.fr/).

## Architecture

```mermaid
flowchart TD
    subgraph Données
        EAD[Fichiers EAD XML\n./data/calames/]
    end

    subgraph Pipeline d'indexation
        PARSER[ead_parser.py\nParsing EAD → Component\nHéritage simple + cumulatif\nPropagation dates bottom-up]
        INDEXER[indexer.py\nBulk vers Elasticsearch\nMapping + analyseur français]
        MS[(Elasticsearch\nIndex: ead_components\n~1,4M documents)]
    end

    subgraph API FastAPI
        direction TB
        HELPERS[filters.py · grouping.py\nbuild_query · build_filters\ngrouped_search]
        SEARCH[/search\nRecherche plein texte\n+ facettes + regroupement]
        NAV[Navigation\n/fonds · /component\n/children · /ancestors]
        PERSONS[Personnes\n/persons · /person]
        NL[/nlsearch\nRecherche NL via LLM]
        SUM[/summarize\nRésumé via LLM]
        PROMPTS[nl_prompt.txt\nsummarize_prompt.txt]
        LLM[LLM OpenAI-compatible\ngemma / gpt / mistral…]
    end

    subgraph Frontend Vue.js
        HOME[HomeView\nListe des fonds]
        SV[SearchView\nRecherche + facettes\n+ mode IA]
        FV[FondsView\nArbre hiérarchique]
        CV[ComponentView\nDétail + navigation]
        PV[PersonsView / PersonView]
    end

    EAD --> PARSER --> INDEXER --> MS
    MS --> HELPERS --> SEARCH & NAV & PERSONS & NL & SUM
    NL & SUM --> PROMPTS --> LLM --> NL & SUM
    SEARCH & NAV & NL & SUM & PERSONS --> HOME & SV & FV & CV & PV
```

### Modules backend (`backend/api/`)

| Module | Rôle |
|---|---|
| `main.py` | Application FastAPI — 11 endpoints |
| `filters.py` | `build_query()` + `build_filters()` + `parse_nl_filters()` — requêtes et filtres Elasticsearch |
| `grouping.py` | `grouped_search()` — regroupement hiérarchique calculé par Elasticsearch sur tous les résultats |
| `llm.py` | `call_llm()` + chargement prompts — client LLM OpenAI-compatible |

---

## Stack technique

| Couche | Outil |
|---|---|
| Parsing XML + indexation | Python + lxml |
| Index de recherche | Elasticsearch 8 |
| API | FastAPI (Python) |
| Frontend | Vue 3 + Vite |

## Structure du projet

```
calames-html/
├── data/
│   ├── calames/           # Fichiers EAD moissonnés depuis Calames (OAI-PMH)
│   └── EAD-corpus/        # Corpus de test (fichiers EAD tiers)
├── backend/
│   ├── indexer/           # Pipeline EAD → Elasticsearch
│   ├── harvester/         # Moissonnage OAI-PMH de Calames
│   └── api/               # API FastAPI
├── frontend/              # Application Vue.js
└── restart-api.ps1        # Script de (re)démarrage de l'API
```

## Lancer le projet

Il existe deux modes de lancement : **avec Docker** (recommandé pour la production et les tests) et **sans Docker** (recommandé pour le développement).

### Ports par mode

| Service | Sans Docker | Avec Docker |
|---|---|---|
| API FastAPI | `:8000` | `:8001` |
| Frontend Vue | `:5173` | `:80` |
| Elasticsearch | `:9200` | `:9200` (interne) |

## Corpus disponibles

Les corpus sont définis dans `corpora.json` :

| Corpus | Index Elasticsearch | Données |
|---|---|---|
| `calames` | `ead_components_calames` | Fichiers EAD Calames |
| `test` | `ead_components_test` | Fichiers EAD de test (`data/test/`) |

Chaque corpus a son propre index Elasticsearch — basculer de l'un à l'autre ne détruit pas l'index de l'autre.

---

## Mode Docker

### Prérequis

- Docker Desktop (Windows/Mac) ou Docker + Docker Compose (Linux)

### Lancement

```bash
docker compose up --build -d
```

L'indexation tourne automatiquement au premier démarrage (~40 min pour l'ensemble des fichiers Calames). Le frontend est accessible sur `http://localhost`.

Pour suivre la progression de l'indexation :

```bash
docker compose logs indexer -f
```

### Configuration

Créer un fichier `.env` à la racine pour surcharger les valeurs par défaut :

```env
ELASTIC_PASSWORD=votre-mot-de-passe
VITE_API_URL=http://mon-serveur.fr:8000   # sur un serveur distant
```

### Commandes utiles

```bash
docker compose up -d          # démarrer sans rebuild
docker compose down           # arrêter
docker compose down -v        # arrêter et supprimer l'index (réindexation complète au prochain démarrage)
docker compose logs api -f    # logs de l'API
docker compose ps             # état des services
```

---

## Mode développement (sans Docker)

### Prérequis

- Python 3.11+
- Node.js 18+
- Docker (Elasticsearch tourne dans le conteneur `calames-es`, créé par `es-dev.ps1`)

### Démarrage rapide (Windows)

```powershell
powershell -File dev.ps1                 # corpus "calames" par défaut
powershell -File dev.ps1 -Corpus test   # corpus "test"
```

Ce script démarre le conteneur Elasticsearch (`es-dev.ps1`), puis lance l'API et le frontend
dans deux fenêtres séparées. Il tue automatiquement les processus existants sur les ports 8000
et 5173 avant de démarrer. L'index de développement est conservé dans le volume Docker
`calames_es_dev`.

Pour tout arrêter :
```powershell
powershell -File stop.ps1
```

Pour relancer uniquement l'API sur un corpus différent :
```powershell
powershell -File restart-api.ps1 -Corpus test
```

Pour indexer un corpus :
```powershell
powershell -File index.ps1               # indexe "calames"
powershell -File index.ps1 -Corpus test  # indexe "test"
```

### Étapes détaillées

#### 1. Dépendances Python (première fois)

```bash
cd backend
pip install -r requirements.txt
```

#### 2. Dépendances frontend (première fois)

```bash
cd frontend
npm install
```

#### 3. Moissonnage des données (une fois, ou en incrémental)

```bash
cd backend/harvester

# Moissonnage complet (→ data/calames/)
python harvester.py

# Moissonnage incrémental (depuis le dernier passage)
python harvester.py --incremental

# Tester sans télécharger
python harvester.py --dry-run --limit 10

# Restreindre à un établissement (setSpec OAI)
python harvester.py --set 751059803
```

#### 4. Indexation (une fois, ou après mise à jour des données)

```bash
cd backend/indexer
python indexer.py ../../data/calames --host http://localhost:9200
```

L'index existant est **toujours supprimé et recréé** avant réindexation (c'est aussi
la seule façon d'appliquer un changement de mapping ou d'analyseur). Avec un Elasticsearch
sécurisé, ajouter `--password <mot de passe de elastic>`.

#### 5. Lancer manuellement les trois services

Dans trois terminaux séparés :

```bash
# Terminal 1 — Elasticsearch
docker run -d --name calames-es -p 9200:9200 -e discovery.type=single-node \
  -e xpack.security.enabled=false -e "ES_JAVA_OPTS=-Xms1g -Xmx1g" \
  -v calames_es_dev:/usr/share/elasticsearch/data \
  docker.elastic.co/elasticsearch/elasticsearch:8.19.3

# Terminal 2 — API
cd backend
ES_HOST=http://localhost:9200 DATA_DIR=../data/calames \
  uvicorn api.main:app --reload --port 8000

# Terminal 3 — Frontend
cd frontend
npm run dev
```

Variables d'environnement de l'API :

| Variable | Défaut | Description |
|---|---|---|
| `ES_HOST` | `http://localhost:9200` | URL d'Elasticsearch |
| `ES_USER` | `elastic` | Utilisateur (utilisé seulement si `ES_PASSWORD` est renseigné) |
| `ES_PASSWORD` | _(vide)_ | Mot de passe (vide = pas d'authentification) |
| `ES_INDEX` | `ead_components` | Nom de l'index |
| `SIBLING_THRESHOLD` | `3` | Seuil de la règle des N frères (`sibling_grouping=true`) |
| `COVERAGE_THRESHOLD` | `0.75` | Seuil de couverture du regroupement par défaut |
| `NL_LLM_BASE_URL` | `https://api.openai.com/v1` | Base URL LLM OpenAI-compatible |
| `NL_LLM_API_KEY` | _(vide)_ | Clé API LLM (si vide : fallback recherche brute) |
| `NL_LLM_MODEL` | `gpt-4o-mini` | Modèle LLM (ex. `gemma-4-31b`, `mistral`, `llama3`) |

Le fichier `frontend/.env.local` configure l'URL de l'API :

```env
VITE_API_URL=http://localhost:8000
```

---

## Endpoints de l'API

| Méthode | URL | Description |
|---|---|---|
| GET | `/fonds` | Liste tous les fonds (composants racine, `depth = 0`) |
| GET | `/fonds/{ead_id}` | Composant racine d'un instrument de recherche |
| GET | `/component?node_id=` | Un composant (valeurs brutes EAD, héritage non appliqué) |
| GET | `/children?node_id=` | Enfants directs d'un composant, triés par position |
| GET | `/ancestors?node_id=` | Chaîne d'ancêtres (fil d'Ariane) |
| GET | `/search` | Recherche plein texte + facettes + regroupement hiérarchique |
| GET | `/nlsearch?q=` | Recherche en langage naturel (LLM → Elasticsearch) |
| GET | `/summarize?q=` | Résumé LLM des résultats d'une recherche |
| GET | `/persons` | Index des personnes avec identifiant IdRef/Sudoc |
| GET | `/person?name=` | Composants associés à une personne (par nom ou IdRef) |
| GET | `/raw?node_id=` | Fragment XML EAD brut d'un composant |

### Paramètres de `/search`

| Paramètre | Type | Description |
|---|---|---|
| `q` | string | Requête plein texte |
| `level` | string | Niveau EAD (`fonds`, `series`, `subseries`, `file`, `item`, `recordgrp`…) |
| `ead_id` | string | Restreindre à un instrument de recherche |
| `date_from` | int | Année de début (inclusive) |
| `date_to` | int | Année de fin (inclusive) |
| `lang` | string | Code langue (`fre`, `eng`, `lat`…) |
| `subject` | string | Sujet (plein texte, dans le champ sujets uniquement) |
| `geo_name` | string | Nom géographique (plein texte, dans ce champ uniquement) |
| `genre_form` | string | Genre / type de document (plein texte, dans ce champ uniquement) |
| `creator` | string | Nom de créateur (plein texte, dans ce champ uniquement) |
| `corp_name` | string | Nom de collectivité (plein texte, dans ce champ uniquement) |
| `pers_name` | string | Nom de personne (plein texte, dans ce champ uniquement) |
| `repository` | string | Institution de conservation |
| `limit` | int | Résultats par page (1–100, défaut 20) |
| `offset` | int | Décalage pour la pagination |
| `sibling_grouping` | bool | Règle des N frères au lieu de la couverture (défaut `false`) |

Tous les mots de `q` doivent être présents, éventuellement répartis sur plusieurs champs ;
une faute de frappe est tolérée à partir de 7 lettres, deux à partir de 11. Chaque paramètre
texte par champ (`subject`, `pers_name`…) doit correspondre **dans son propre champ**, en plus
de `q`.

La réponse contient `total` (nombre exact d'entrées après regroupement) et `total_hits`
(nombre exact de composants correspondants). Les facettes comptent les composants
correspondants. La pagination va jusqu'à 10 000 entrées (`offset` ≤ 9 900).

---

## Indexation

### Héritage des champs

Les champs sont résolus à l'indexation selon deux modes :

**Héritage simple** — le plus proche ancêtre remplace le vide : langue, date, conditions d'accès, conditions d'utilisation, organisme responsable.

**Héritage cumulatif** — les valeurs s'accumulent sans doublon : sujets, noms géographiques, genres/formes, noms de collectivités, noms de personnes.

### Compatibilité EAD

Le parser gère :
- EAD 2002 avec ou sans namespace (`urn:isbn:1-931666-22-9`)
- `<c>` directs ou encapsulés dans un ou plusieurs `<dsc>`
- `id` ou `xml:id` sur les composants (repli sur identifiant auto-généré)
- Niveaux EAD variés : `fonds`, `recordgrp`, `series`, `subseries`, `file`, `item`…

### Regroupement hiérarchique

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
