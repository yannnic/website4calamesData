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
        INDEXER[indexer.py\nBatch vers MeiliSearch\nConfig index + typo tolerance]
        MS[(MeiliSearch\nIndex: ead_components\n~1,4M documents)]
    end

    subgraph API FastAPI
        direction TB
        HELPERS[filters.py · pruning.py\nms_escape · build_filters\napply_sibling_grouping\napply_smart_pruning]
        SEARCH[/search\nRecherche plein texte\n+ facettes + pruning]
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
| `filters.py` | `ms_escape()` + `build_filters()` — filtres MeiliSearch sécurisés |
| `pruning.py` | `apply_sibling_grouping()` + `apply_smart_pruning()` — regroupement hiérarchique |
| `llm.py` | `call_llm()` + chargement prompts — client LLM OpenAI-compatible |

---

## Stack technique

| Couche | Outil |
|---|---|
| Parsing XML + indexation | Python + lxml |
| Index de recherche | MeiliSearch |
| API | FastAPI (Python) |
| Frontend | Vue 3 + Vite |

## Structure du projet

```
calames-html/
├── data/
│   ├── calames/           # Fichiers EAD moissonnés depuis Calames (OAI-PMH)
│   └── EAD-corpus/        # Corpus de test (fichiers EAD tiers)
├── backend/
│   ├── indexer/           # Pipeline EAD → MeiliSearch
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
| MeiliSearch | `:7700` | `:7700` (interne) |

## Corpus disponibles

Les corpus sont définis dans `corpora.json` :

| Corpus | Index MeiliSearch | Données |
|---|---|---|
| `calames` | `ead_components_calames` | Fichiers EAD Calames |
| `test` | `ead_components_test` | Fichiers EAD de test (`data/test/`) |

Chaque corpus a son propre index MeiliSearch — basculer de l'un à l'autre ne détruit pas l'index de l'autre.

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
MEILI_MASTER_KEY=votre-clé-secrète
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
- `meilisearch.exe` (Windows) ou `meilisearch` (Linux/Mac) à la racine du projet

### Démarrage rapide (Windows)

```powershell
powershell -File dev.ps1                 # corpus "calames" par défaut
powershell -File dev.ps1 -Corpus test   # corpus "test"
```

Ce script lance MeiliSearch, l'API et le frontend dans trois fenêtres séparées.
Il tue automatiquement les processus existants sur les ports 7700, 8000 et 5173 avant de démarrer.

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
python indexer.py ../../data/calames --host http://localhost:7700 --api-key changeme
```

L'index existant est **toujours vidé** avant réindexation.

#### 5. Lancer manuellement les trois services

Dans trois terminaux séparés :

```bash
# Terminal 1 — MeiliSearch
./meilisearch --master-key changeme

# Terminal 2 — API
cd backend
MEILI_HOST=http://localhost:7700 MEILI_KEY=changeme DATA_DIR=../data/calames \
  uvicorn api.main:app --reload --port 8000

# Terminal 3 — Frontend
cd frontend
npm run dev
```

Variables d'environnement de l'API :

| Variable | Défaut | Description |
|---|---|---|
| `MEILI_HOST` | `http://localhost:7700` | URL de MeiliSearch |
| `MEILI_KEY` | _(vide)_ | Clé d'API MeiliSearch |
| `MEILI_INDEX` | `ead_components` | Nom de l'index |
| `SIBLING_THRESHOLD` | `3` | Seuil de regroupement par parent |
| `COVERAGE_THRESHOLD` | `0.75` | Seuil de couverture pour le pruning intelligent |
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
| GET | `/search` | Recherche plein texte + facettes + pruning hiérarchique |
| GET | `/nlsearch?q=` | Recherche en langage naturel (LLM → MeiliSearch) |
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
| `subject` | string | Sujet (valeur exacte) |
| `geo_name` | string | Nom géographique (valeur exacte) |
| `genre_form` | string | Genre / type de document |
| `creator` | string | Nom de créateur (valeur exacte) |
| `corp_name` | string | Nom de collectivité |
| `pers_name` | string | Nom de personne |
| `repository` | string | Institution de conservation |
| `limit` | int | Résultats par page (1–100, défaut 20) |
| `offset` | int | Décalage pour la pagination |
| `sibling_grouping` | bool | Regroupement par parent (défaut `false`) |

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

### Regroupement par parent (`sibling_grouping`)

Si ≥ `SIBLING_THRESHOLD` résultats partagent le même parent, ils sont remplacés par ce parent (récursif). Désactivé par défaut ; à activer pour des requêtes générales.
