"""
Calames HTML — FastAPI backend.

Endpoints :
  GET /persons            Index des personnes avec identifiant IdRef/Sudoc
  GET /fonds              Liste de tous les instruments de recherche (niveau fonds)
  GET /fonds/{ead_id}     Composant racine d'un instrument de recherche
  GET /component          Un composant EAD (par node_id)
  GET /resolve            Composant d'une adresse Calames (/pub/ms/<id>)
  GET /children           Enfants directs d'un composant
  GET /ancestors          Chaîne des ancêtres (fil d'Ariane)
  GET /subtree            Sous-arbre complet d'un composant, avec descriptions (petit sous-arbre)
  GET /raw                Fragment XML EAD brut d'un composant
  GET /search             Recherche plein texte avec regroupement hiérarchique
  GET /nlsearch           Recherche en langage naturel (via LLM)
  GET /summarize          Résumé LLM des résultats d'une recherche
  GET /llm/check          Vérifie la configuration du LLM
  GET /person             Composants associés à une personne
  GET /files              Fichiers EAD du dossier et statut d'indexation
  POST /upload            Dépôt d'un fichier EAD (jeton UPLOAD_TOKEN requis)

Paramètre commun : corpus=test interroge le corpus de test (fichiers ad hoc de
data/test), indexé automatiquement au démarrage de l'API.

LLM : configuré par le client (en-têtes X-LLM-Base-Url, X-LLM-Api-Key, X-LLM-Model,
page Paramètres du frontend), à défaut par NL_LLM_* (voir llm.py).

Dépendances : Elasticsearch (ES_HOST), LLM OpenAI-compatible
Variables d'environnement : voir README.md
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
import threading
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Optional

from elasticsearch import Elasticsearch, NotFoundError
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from lxml import etree

from .filters import (
    SEARCH_FACETS,
    SORTS,
    build_filters,
    build_query,
    facet_aggs,
    facet_distribution,
    hits_of,
    parse_nl_filters,
    total_of,
)
from .llm import (
    NOT_CONFIGURED,
    LLMConfig,
    call_llm,
    llm_config,
    load_nl_prompt,
    load_summarize_prompt,
)
from .grouping import grouped_search

# The indexer modules import each other flat (run from backend/indexer).
sys.path.insert(0, str(Path(__file__).parent.parent / "indexer"))
from ead_parser import find_element, strip_child_components  # noqa: E402
from indexer import index_directory  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration (environment variables with sensible defaults)
# ---------------------------------------------------------------------------

ES_HOST     = os.getenv("ES_HOST", "http://localhost:9200")
ES_USER     = os.getenv("ES_USER", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")
ES_INDEX    = os.getenv("ES_INDEX", "ead_components")
DATA_DIR    = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent.parent / "data" / "calames"))

# Organismes responsables : adresse, téléphone, courriel, site, par RCR
# (etablissements.json dans le dossier EAD, produit par le moissonneur).
_ETABLISSEMENTS: dict[Path, tuple[float, dict]] = {}


def _etablissement(rcr: str) -> Optional[dict]:
    path = _data_dir() / "etablissements.json"
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return None
    cached = _ETABLISSEMENTS.get(path)
    if cached is None or cached[0] != mtime:
        cached = _ETABLISSEMENTS[path] = (mtime, json.loads(path.read_text(encoding="utf-8")))
    return cached[1].get(rcr)


def _with_details(doc: dict) -> dict:
    """A component as displayed on its page: descendants count, holding institution."""
    info = _etablissement(doc.get("repository_id") or "")
    return {**doc, "descendants_count": _descendants_count(doc["node_id"]),
            **({"repository_info": info} if info else {})}


# Corpus de test (?corpus=test) : réindexé à chaque démarrage de l'API.
TEST_ES_INDEX = os.getenv("TEST_ES_INDEX", "ead_components_test")
TEST_DATA_DIR = Path(os.getenv("TEST_DATA_DIR", Path(__file__).parent.parent.parent / "data" / "test"))

# Dépôt de fichiers (désactivé si UPLOAD_TOKEN est vide)
UPLOAD_TOKEN   = os.getenv("UPLOAD_TOKEN", "")
MAX_UPLOAD_MB  = int(os.getenv("MAX_UPLOAD_MB", "20"))
WATCHER_STATE  = Path(os.getenv("STATE_FILE", "/state/watcher.json"))


# ---------------------------------------------------------------------------
# Elasticsearch client (shared, initialised at startup)
# ---------------------------------------------------------------------------

_es: Elasticsearch

# Corpus of the current request, set by _select_corpus.
_test_corpus: ContextVar[bool] = ContextVar("test_corpus", default=False)


async def _select_corpus(
    corpus: Optional[str] = Query(default=None, description="« test » : corpus de test (fichiers ad hoc)"),
) -> None:
    # Async so that the value is set in the request's context, which sync
    # endpoints inherit when run in the thread pool.
    if corpus not in (None, "", "test"):
        raise HTTPException(status_code=400, detail=f"Corpus inconnu : {corpus}")
    _test_corpus.set(corpus == "test")


def _llm(
    x_llm_base_url: str = Header(default="", description="URL de base OpenAI-compatible"),
    x_llm_api_key: str = Header(default="", description="Clé API du LLM"),
    x_llm_model: str = Header(default="", description="Modèle"),
) -> LLMConfig:
    return llm_config(x_llm_base_url.strip(), x_llm_api_key.strip(), x_llm_model.strip())


def _index() -> str:
    return TEST_ES_INDEX if _test_corpus.get() else ES_INDEX


def _data_dir() -> Path:
    return TEST_DATA_DIR if _test_corpus.get() else DATA_DIR


def _search(**kwargs: Any) -> Any:
    """Run a search on the components index (exact total hit count)."""
    return _es.search(index=_index(), track_total_hits=True, **kwargs)


def _index_test_corpus() -> None:
    if TEST_ES_INDEX == ES_INDEX or not any(TEST_DATA_DIR.glob("*.xml")):
        return  # corpus principal = corpus de test (dev.ps1 -Corpus test), ou pas de fichiers
    try:
        index_directory(TEST_DATA_DIR, ES_HOST, ES_USER, ES_PASSWORD, TEST_ES_INDEX)
    except Exception as exc:
        print(f"[corpus test] indexation impossible : {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _es
    _es = Elasticsearch(ES_HOST, basic_auth=(ES_USER, ES_PASSWORD) if ES_PASSWORD else None,
                        request_timeout=30)
    _index_test_corpus()
    _prompt_dir = Path(__file__).parent
    try:
        # Pre-fetch facet values to generate a live NL prompt with real index data.
        res = _search(size=0, aggs=facet_aggs(["genre_forms_norm", "gff_norm", "tdd_norm", "technique_norm"], 2000))
        dist = facet_distribution(res)

        def _top(field: str, n: int = 50) -> str:
            vals = sorted(dist.get(field, {}).keys())
            return ", ".join(vals[:n]) if vals else "—"

        gff  = _top("gff_norm")
        tdd  = _top("tdd_norm")
        tech = _top("technique_norm")
        typed_lines = []
        if gff  != "—": typed_lines.append(f"- gff_norm : genre/forme au sens strict — valeurs connues : {gff}")
        if tdd  != "—": typed_lines.append(f"- tdd_norm : type de document — valeurs connues : {tdd}")
        if tech != "—": typed_lines.append(f"- technique_norm : technique artistique — valeurs connues : {tech}")

        facet_values = {
            "genre_forms_values":      _top("genre_forms_norm"),
            "typed_genreform_section": "\n".join(typed_lines),
        }
        template = (_prompt_dir / "nl_prompt.txt").read_text(encoding="utf-8").strip()
        live = template
        for k, v in facet_values.items():
            live = live.replace(f"{{{k}}}", v)
        (_prompt_dir / "nl_prompt_live.txt").write_text(live, encoding="utf-8")
        print("[nlsearch] nl_prompt_live.txt généré.")
    except Exception as exc:
        print(f"[nlsearch] facet preload failed: {exc}")
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Calames HTML API",
    description="Search and navigation API for EAD archival finding aids.",
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(_select_corpus)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_by_id(node_id: str) -> dict:
    """Fetch a single document by node_id (the Elasticsearch _id)."""
    try:
        return _es.get(index=_index(), id=node_id)["_source"]
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Component not found: {node_id}")


def _fold(s: str) -> str:
    """Lowercase and strip diacritics."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


# Accented variants of each base letter, for accent-insensitive term regexps.
_LETTER_VARIANTS = {
    "a": "aàâäáã", "c": "cç", "e": "eéèêë", "i": "iîïíì", "n": "nñ",
    "o": "oôöóòø", "u": "uûüùú", "y": "yÿý",
}


def _regexp_escape(s: str) -> str:
    """Escape a literal for a Lucene regexp (every non-alphanumeric char)."""
    return "".join(c if c.isalnum() else "\\" + c for c in s)


def _prefix_regexp(prefix: str) -> str:
    """Lucene regexp matching terms that start with `prefix`, ignoring case and accents."""
    out = []
    for ch in prefix:
        base = _fold(ch)
        if base.isalpha() and len(base) == 1:
            variants = _LETTER_VARIANTS.get(base, base)
            out.append("[" + variants + variants.upper() + "]")
        else:
            out.append(_regexp_escape(ch))
    return "".join(out) + ".*"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/persons", summary="List persons with IdRef/Sudoc ID (facet browse)")
def list_persons(
    letter: Optional[str] = Query(default=None, description="Starting letter (A–Z)"),
    prefix: Optional[str] = Query(default=None, description="2-3 letter prefix for drill-down"),
    q: Optional[str] = Query(default=None, description="Free-text search in person names"),
) -> dict:
    """
    Return persons that have an IdRef/Sudoc identifier.
    Results are sourced from the pers_name_ids field ("Name||id" entries).
    letter/prefix: names starting with it (accent-insensitive), alphabetical order.
    q: names containing every word of q as a word prefix, most frequent first.
    Returns up to 500 persons + has_more flag for sub-level navigation.
    """
    LIMIT = 500

    if q:
        # Pre-select components naming such a person, then check each name.
        words = _fold(q).split()
        res = _search(
            size=0,
            query={"match": {"pers_names": {"query": q, "operator": "and"}}},
            aggs={"p": {"terms": {"field": "pers_name_ids", "size": 5000}}},
        )
        buckets = [
            b for b in res["aggregations"]["p"]["buckets"]
            if all(any(w2.startswith(w) for w2 in re.split(r"[^\w]+", _fold(b["key"].split("||")[0])))
                   for w in words)
        ]
    else:
        terms: dict[str, Any] = {"field": "pers_name_ids", "size": LIMIT + 1, "order": {"_key": "asc"}}
        if prefix or letter:
            terms["include"] = _prefix_regexp(prefix or letter)
        res = _search(size=0, aggs={"p": {"terms": terms}})
        buckets = res["aggregations"]["p"]["buckets"]

    has_more = len(buckets) > LIMIT
    buckets = buckets[:LIMIT]

    # Parse "Name||idref_id" entries, deduplicate by name.
    seen: set[str] = set()
    persons = []
    for bucket in buckets:
        v = bucket["key"]
        if "||" not in v:
            continue
        name, idref_id = v.rsplit("||", 1)
        if name not in seen:
            seen.add(name)
            persons.append({"name": name, "idref_id": idref_id, "count": bucket["doc_count"]})

    return {"persons": persons, "has_more": has_more}


@app.get("/fonds", summary="List all finding aids")
def list_fonds() -> list[dict]:
    """Return the top-level components (files not attached under another file)."""
    result = _search(
        query={"term": {"depth": 0}},
        size=1000,
        source_includes=[
            "node_id", "ead_id", "title", "unitid",
            "date_display", "date_normal", "date_start", "date_end",
            "repository", "repository_id", "creators", "abstract", "languages",
            "children_count", "file_comment",
        ],
    )
    return hits_of(result)


@app.get("/fonds/{ead_id}", summary="Get root component of a finding aid")
def get_fonds(ead_id: str) -> dict:
    """Return the root (archdesc) component of a given EAD file, attached or not."""
    result = _search(
        query={"bool": {"filter": [{"term": {"ead_id": ead_id}}, {"term": {"file_root": True}}]}},
        size=1,
    )
    hits = hits_of(result)
    if not hits:
        raise HTTPException(status_code=404, detail=f"Finding aid not found: {ead_id}")
    return _with_details(hits[0])


@app.get("/component", summary="Get a single component")
def get_component(node_id: str = Query(..., description="Component node_id")) -> dict:
    return _with_details(_get_by_id(node_id))


@app.get("/resolve", summary="Composant d'une adresse Calames")
def resolve(id: str = Query(..., description="Identifiant Calames : FileId-<N> ou @id d'un composant")) -> dict:
    """
    Component designated by a Calames identifier, as in its URLs
    https://calames.abes.fr/pub/ms/<id> : "FileId-<N>" (root of a file) or the
    @id of a component. The frontend redirects /pub/ms/<id> with it.
    """
    m = re.fullmatch(r"FileId-(\d+)", id.strip(), re.I)
    # A file merged into the head of its succession chain leads to the head.
    query = ({"bool": {"should": [
                {"bool": {"filter": [{"term": {"file_id": m.group(1)}}, {"term": {"file_root": True}}]}},
                {"term": {"merged_file_ids": m.group(1)}},
             ], "minimum_should_match": 1}}
             if m else {"term": {"xml_id": id.strip()}})
    hits = hits_of(_search(query=query, size=1, source_includes=["node_id", "ead_id", "depth"]))
    if not hits:
        raise HTTPException(status_code=404, detail=f"Identifiant Calames inconnu : {id}")
    return hits[0]


# Fields of a component in the navigation tree; with its description (details).
TREE_FIELDS = [
    "node_id", "ead_id", "level", "depth", "parent_id",
    "unitid", "title", "date_display", "date_normal",
    "date_start", "date_end", "extents", "access_restrict",
    "children_count",
]
DETAIL_FIELDS = TREE_FIELDS + ["abstract", "scope_content", "biography", "phys_facets", "file_root"]

# /subtree refuses larger subtrees (the frontend offers it from a lower threshold).
SUBTREE_MAX = 500


def _descendants_count(node_id: str) -> int:
    """Number of components below node_id, attached files included (liaisons)."""
    return _es.count(index=_index(), query={"term": {"ancestor_ids": node_id}})["count"]


def _descendants_counts(node_ids: list[str]) -> dict[str, int]:
    """Number of descendants of each node, in one aggregation."""
    if not node_ids:
        return {}
    res = _search(size=0, query={"terms": {"ancestor_ids": node_ids}},
                  aggs={"d": {"terms": {"field": "ancestor_ids", "include": node_ids,
                                        "size": len(node_ids)}}})
    return {b["key"]: b["doc_count"] for b in res["aggregations"]["d"]["buckets"]}


@app.get("/children", summary="Get direct children of a component")
def get_children(
    node_id: str = Query(..., description="Parent node_id"),
    details: bool = Query(default=False, description="Inclure la description de chaque enfant"),
) -> list[dict]:
    """
    Return direct children of a component, in EAD document order, each with its
    number of descendants (descendants_count).
    """
    result = _search(
        query={"term": {"parent_id": node_id}},
        sort=[{"position": "asc"}],
        size=10000,
        source_includes=DETAIL_FIELDS if details else TREE_FIELDS,
    )
    hits = hits_of(result)
    counts = _descendants_counts([h["node_id"] for h in hits if h.get("children_count")])
    for h in hits:
        h["descendants_count"] = counts.get(h["node_id"], 0)
    return hits


@app.get("/subtree", summary="Sous-arbre d'un composant, avec descriptions")
def get_subtree(
    node_id: str = Query(..., description="Component node_id"),
    max: int = Query(default=200, ge=1, le=SUBTREE_MAX, description="Taille maximale acceptée"),
) -> dict:
    """
    Every component below node_id, with its description, sorted by depth then
    position (the client rebuilds the tree from parent_id). Refused (413) above
    `max` components: the tree is then opened level by level.
    """
    total = _descendants_count(node_id)
    if total > max:
        raise HTTPException(status_code=413,
                            detail=f"Sous-arbre de {total} composants (maximum {max}).")
    result = _search(
        query={"term": {"ancestor_ids": node_id}},
        sort=[{"depth": "asc"}, {"position": "asc"}],
        size=max,
        source_includes=DETAIL_FIELDS,
    )
    return {"total": total, "nodes": hits_of(result)}


@app.get("/ancestors", summary="Get ancestor chain (breadcrumb)")
def get_ancestors(node_id: str = Query(..., description="Component node_id")) -> list[dict]:
    """
    Return the list of ancestors from root to direct parent, suitable for
    building a breadcrumb. The component itself is not included.
    """
    comp = _get_by_id(node_id)
    ancestor_ids: list[str] = comp.get("ancestor_ids", [])
    if not ancestor_ids:
        return []

    # mget returns the documents in the order of ancestor_ids (root first).
    result = _es.mget(
        index=_index(),
        ids=ancestor_ids,
        source_includes=["node_id", "level", "depth", "title", "unitid", "ead_id"],
    )
    return [d["_source"] for d in result["docs"] if d.get("found")]


_parser_lock = threading.Lock()


@app.get("/raw", summary="Raw EAD XML for a component", response_class=PlainTextResponse)
def get_raw(
    node_id: str = Query(..., description="Component node_id"),
    children: bool = Query(default=False, description="Inclure les composants <c> descendants"),
) -> str:
    """
    Return the raw EAD XML fragment for a component. By default its <c>
    children are replaced by a comment (a fonds would otherwise be the whole file).
    """
    doc = _get_by_id(node_id)
    source_file = doc.get("source_file")
    if not source_file:
        raise HTTPException(status_code=404, detail="Source file not recorded for this component (reindex needed)")

    ead_path = _data_dir() / source_file
    if not ead_path.exists():
        ead_path = _data_dir().parent / source_file
    if not ead_path.exists():
        raise HTTPException(status_code=404, detail=f"EAD file not found: {source_file}")

    # The parser keeps the file's namespace in a module global: one file at a time.
    with _parser_lock:
        el = find_element(ead_path, node_id)
        if el is not None and not children:
            strip_child_components(el)
    if el is None:
        raise HTTPException(status_code=404, detail=f"Component '{node_id}' not found in {source_file}")

    return etree.tostring(el, encoding="unicode", pretty_print=True)


@app.get("/files", summary="EAD files and their indexing status")
def list_files() -> dict:
    """
    List the .xml files of DATA_DIR with the status written by the watcher :
    pending (pas encore vu), indexing, indexed, error.
    """
    if _test_corpus.get():
        # Indexé au démarrage de l'API, sans watcher ; pas de dépôt.
        return {"upload_enabled": False, "files": [
            {"name": p.name, "size": p.stat().st_size, "status": "indexed",
             "docs": None, "error": None, "updated_at": None}
            for p in sorted(TEST_DATA_DIR.glob("*.xml"))]}
    try:
        state = json.loads(WATCHER_STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    files = []
    for p in sorted(DATA_DIR.glob("*.xml"), key=lambda p: p.stat().st_mtime, reverse=True):
        st = p.stat()
        info = state.get(p.name, {})
        stale = (info.get("mtime"), info.get("size")) != (st.st_mtime, st.st_size)
        files.append({
            "name": p.name,
            "size": st.st_size,
            "status": "pending" if stale else info.get("status", "pending"),
            "docs": None if stale else info.get("docs"),
            "error": None if stale else info.get("error"),
            "updated_at": info.get("updated_at"),
        })
    return {"upload_enabled": bool(UPLOAD_TOKEN), "files": files}


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@app.post("/upload", summary="Upload an EAD file (indexed asynchronously by the watcher)")
async def upload(
    file: UploadFile = File(...),
    x_upload_token: str = Header(default=""),
) -> dict:
    if not UPLOAD_TOKEN:
        raise HTTPException(status_code=403, detail="Le dépôt de fichiers est désactivé sur ce serveur.")
    if _test_corpus.get():
        raise HTTPException(status_code=403, detail="Pas de dépôt dans le corpus de test.")
    if not secrets.compare_digest(x_upload_token, UPLOAD_TOKEN):
        raise HTTPException(status_code=401, detail="Jeton de dépôt invalide.")

    name = _SAFE_NAME.sub("_", Path(file.filename or "").name).strip("._")
    if not name.lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail="Le fichier doit avoir l'extension .xml.")

    content = await file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Fichier trop volumineux (max {MAX_UPLOAD_MB} Mo).")

    try:
        root = etree.fromstring(content, parser=etree.XMLParser(
            load_dtd=False, no_network=True, resolve_entities=False,
        ))
    except etree.XMLSyntaxError as exc:
        raise HTTPException(status_code=400, detail=f"XML mal formé : {exc}")
    if etree.QName(root).localname != "ead":
        raise HTTPException(status_code=400, detail="L'élément racine doit être <ead>.")

    # Écriture atomique : le watcher ne voit jamais un fichier partiel.
    dest = DATA_DIR / name
    tmp = DATA_DIR / f".{name}.part"
    tmp.write_bytes(content)
    os.replace(tmp, dest)
    return {"name": name, "status": "pending"}


@app.get("/search", summary="Full-text search")
def search(
    q: str = Query(default="", description="Search query"),
    # Structural filters
    level: Optional[str] = Query(default=None, description="EAD level (fonds, series, subseries, file, item)"),
    ead_id: Optional[str] = Query(default=None, description="Restrict to a specific finding aid"),
    # Date range
    date_from: Optional[int] = Query(default=None, description="Earliest year (inclusive)"),
    date_to: Optional[int] = Query(default=None, description="Latest year (inclusive)"),
    # Controlled-access filters (exact match on indexed values)
    lang: Optional[str] = Query(default=None, description="Language code (fre, eng, lat, …)"),
    subject: Optional[str] = Query(default=None, description="Subject (full-text in subjects field)"),
    subject_norm: Optional[str] = Query(default=None, description="Subject (exact canonical form — for facet clicks)"),
    geo_name: Optional[str] = Query(default=None, description="Geographic name (full-text)"),
    geo_name_norm: Optional[str] = Query(default=None, description="Geographic name (exact canonical — for facet clicks)"),
    genre_form: Optional[str] = Query(default=None, description="Genre / document type (full-text)"),
    genre_form_norm: Optional[str] = Query(default=None, description="Genre/form (exact canonical — for facet clicks)"),
    gff_norm: Optional[str] = Query(default=None, description="Genre/forme strict (genreform[@type='genre'])"),
    gff_norm_excl: Optional[str] = Query(default=None),
    tdd_norm: Optional[str] = Query(default=None, description="Type de document (genreform[@type='type_de_document'])"),
    tdd_norm_excl: Optional[str] = Query(default=None),
    technique_norm: Optional[str] = Query(default=None, description="Technique artistique (genreform[@type='technique'])"),
    technique_norm_excl: Optional[str] = Query(default=None),
    creator: Optional[str] = Query(default=None, description="Creator name (full-text)"),
    corp_name: Optional[str] = Query(default=None, description="Corporate name (full-text)"),
    corp_name_norm: Optional[str] = Query(default=None, description="Corporate name (exact canonical — for facet clicks)"),
    pers_name: Optional[str] = Query(default=None, description="Personal name (full-text)"),
    pers_name_role: Optional[str] = Query(default=None, description="'Name::role' exact pair"),
    # Repository
    repository: Optional[str] = Query(default=None, description="Holding institution (label)"),
    repository_id: Optional[str] = Query(default=None, description="Holding institution (authfilenumber)"),
    # Period facet
    century: Optional[str] = Query(default=None, description="Century label (e.g. 'XXe s.')"),
    # Exclusion filters (same facets, negative match)
    level_excl: Optional[str] = Query(default=None, description="Exclude EAD level"),
    subject_norm_excl: Optional[str] = Query(default=None, description="Exclude subject (canonical)"),
    geo_name_norm_excl: Optional[str] = Query(default=None, description="Exclude geographic name (canonical)"),
    genre_form_norm_excl: Optional[str] = Query(default=None, description="Exclude genre/form (canonical)"),
    repository_excl: Optional[str] = Query(default=None, description="Exclude institution"),
    century_excl: Optional[str] = Query(default=None, description="Exclude century"),
    # Other indexing terms, provenance, digital copies
    work_title: Optional[str] = Query(default=None, description="Titre d'œuvre (texte libre)"),
    function: Optional[str] = Query(default=None, description="Fonction (texte libre)"),
    provenance: Optional[str] = Query(default=None, description="Propriétaire précédent (forme exacte)"),
    dao: bool = Query(default=False, description="Seulement les composants avec version numérique"),
    # Pagination & options
    sort: str = Query(default="relevance", pattern="^(" + "|".join(SORTS) + ")$",
                      description="relevance, title_asc, title_desc, date_asc, date_desc"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=9900),
    sibling_grouping: bool = Query(default=False, description="Group by the N-siblings rule instead of coverage"),
) -> dict[str, Any]:
    """
    Full-text search across all indexed EAD components.

    `q` is searched across title, abstract, scope/content, biography,
    unitid, creator names, subjects, geographic names, genre/forms,
    corporate names, personal names, and physical facets.

    Field-specific text params (subject, geo_name, …) must each match in their
    own field, in addition to `q` (which is searched across all fields).

    Hierarchical grouping (see grouping.py): with a text query and no `level`
    filter, a parent replaces its matching descendants when enough of its
    children match (coverage rule, or N-siblings rule with `sibling_grouping`).
    `total` counts the grouped entries, `total_hits` the matching components.
    """
    filters = build_filters(
        level=level, level_excl=level_excl,
        ead_id=ead_id,
        date_from=date_from, date_to=date_to,
        lang=lang, pers_name_role=pers_name_role,
        subject_norm=subject_norm, subject_norm_excl=subject_norm_excl,
        geo_name_norm=geo_name_norm, geo_name_norm_excl=geo_name_norm_excl,
        genre_form_norm=genre_form_norm, genre_form_norm_excl=genre_form_norm_excl,
        gff_norm=gff_norm, gff_norm_excl=gff_norm_excl,
        tdd_norm=tdd_norm, tdd_norm_excl=tdd_norm_excl,
        technique_norm=technique_norm, technique_norm_excl=technique_norm_excl,
        corp_name_norm=corp_name_norm,
        repository_id=repository_id, repository=repository, repository_excl=repository_excl,
        century=century, century_excl=century_excl,
        provenance=provenance, dao=dao,
    )

    # Field-specific text terms: each one must match in its own field.
    TEXT_FIELD_ATTRS: list[tuple[str | None, str]] = [
        (subject,    "subjects"),
        (geo_name,   "geo_names"),
        (genre_form, "genre_forms"),
        (creator,    "creator_names"),
        (corp_name,  "corp_names"),
        (pers_name,  "pers_names"),
        (work_title, "work_titles"),
        (function,   "functions"),
    ]
    field_terms = [(attr, val) for val, attr in TEXT_FIELD_ATTRS if val]
    has_text = bool(q or field_terms)

    query = build_query(q, field_terms, filters)
    aggs = facet_aggs(SEARCH_FACETS)

    # With a level filter all results are at the same depth: nothing to group.
    if sibling_grouping or (has_text and not level):
        res = grouped_search(_search, query, "siblings" if sibling_grouping else "coverage",
                             offset, limit, aggs, sort=SORTS[sort])
    else:
        result = _search(query=query, from_=offset, size=limit, aggs=aggs,
                         **({"sort": SORTS[sort]} if SORTS[sort] else {}))
        res = {"hits": hits_of(result), "total": total_of(result),
               "total_hits": total_of(result), "facets": facet_distribution(result)}

    return {
        "query":      q,
        "total":      res["total"],
        "total_hits": res["total_hits"],
        "offset":     offset,
        "limit":      limit,
        "hits":       res["hits"],
        "facets":     res["facets"],
    }


@app.get("/nlsearch", summary="Recherche en langage naturel")
async def nl_search(
    q: str = Query(..., description="Requête en langage naturel"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=9900),
    llm: LLMConfig = Depends(_llm),
) -> dict[str, Any]:
    """
    Traduit une phrase en langage naturel en requête de recherche via un LLM,
    puis exécute la recherche.

    Sans LLM configuré (ou en cas d'erreur), effectue une recherche plein texte
    brute sur q ; `interpreted.error` en donne la raison.
    Le champ `interpreted` expose la traduction effectuée par le LLM.
    """
    interpreted: dict = {"q": q, "filters": [], "explanation": ""}

    if not llm.enabled:
        interpreted["error"] = NOT_CONFIGURED
    else:
        try:
            import json as _json
            system = load_nl_prompt()
            print(f"\n[nlsearch] model={llm.model} base_url={llm.base_url} ({llm.source})")
            print(f"[nlsearch] user: {q}")
            raw = call_llm(llm, system, q, max_tokens=400, temperature=0)
            print(f"[nlsearch] response: {raw}")
            parsed = _json.loads(raw)
            interpreted = {
                "q":           parsed.get("q", q),
                "filters":     parsed.get("filters", []),
                "explanation": parsed.get("explanation", ""),
                "llm_raw":     raw,
            }
        except Exception as exc:
            print(f"[nlsearch] error: {exc}")
            interpreted["error"] = f"Erreur du LLM : {exc}"

    query = build_query(interpreted["q"], [], parse_nl_filters(interpreted["filters"]))
    aggs = facet_aggs(SEARCH_FACETS)
    if interpreted["q"]:
        res = grouped_search(_search, query, "coverage", offset, limit, aggs)
    else:
        result = _search(query=query, from_=offset, size=limit, aggs=aggs)
        res = {"hits": hits_of(result), "total": total_of(result),
               "total_hits": total_of(result), "facets": facet_distribution(result)}

    return {
        "natural_query": q,
        "interpreted":   interpreted,
        "total":         res["total"],
        "total_hits":    res["total_hits"],
        "offset":        offset,
        "limit":         limit,
        "hits":          res["hits"],
        "facets":        res["facets"],
    }


@app.get("/summarize", summary="Résumé LLM des résultats d'une recherche")
async def summarize_results(
    q: str = Query(default="", description="Requête de recherche"),
    n: int = Query(default=10, ge=1, le=50, description="Nombre de résultats à analyser en détail"),
    nl_filters: Optional[str] = Query(default=None, description="Filtres LLM (JSON array) issus de /nlsearch"),
    subject: Optional[str] = Query(default=None, description="Sujet texte libre"),
    geo_name: Optional[str] = Query(default=None, description="Lieu texte libre"),
    genre_form: Optional[str] = Query(default=None, description="Genre/forme texte libre"),
    creator: Optional[str] = Query(default=None, description="Créateur texte libre"),
    corp_name: Optional[str] = Query(default=None, description="Collectivité texte libre"),
    pers_name: Optional[str] = Query(default=None, description="Personne texte libre"),
    level: Optional[str] = Query(default=None),
    level_excl: Optional[str] = Query(default=None),
    date_from: Optional[int] = Query(default=None),
    date_to: Optional[int] = Query(default=None),
    lang: Optional[str] = Query(default=None),
    subject_norm: Optional[str] = Query(default=None),
    subject_norm_excl: Optional[str] = Query(default=None),
    geo_name_norm: Optional[str] = Query(default=None),
    geo_name_norm_excl: Optional[str] = Query(default=None),
    genre_form_norm: Optional[str] = Query(default=None),
    genre_form_norm_excl: Optional[str] = Query(default=None),
    gff_norm: Optional[str] = Query(default=None),
    gff_norm_excl: Optional[str] = Query(default=None),
    tdd_norm: Optional[str] = Query(default=None),
    tdd_norm_excl: Optional[str] = Query(default=None),
    technique_norm: Optional[str] = Query(default=None),
    technique_norm_excl: Optional[str] = Query(default=None),
    corp_name_norm: Optional[str] = Query(default=None),
    repository: Optional[str] = Query(default=None),
    repository_id: Optional[str] = Query(default=None),
    repository_excl: Optional[str] = Query(default=None),
    century: Optional[str] = Query(default=None),
    century_excl: Optional[str] = Query(default=None),
    llm: LLMConfig = Depends(_llm),
) -> dict[str, Any]:
    """
    Effectue la recherche, puis demande au LLM de synthétiser les résultats.
    Les facettes couvrent l'ensemble des résultats ; le détail porte sur les n premiers.
    En mode NL, passer nl_filters (JSON array des filtres textuels issus de /nlsearch).
    """
    import json as _json
    # Termes texte libre restreints à leur champ (comme /search)
    field_terms = [(attr, val) for val, attr in [
        (subject, "subjects"), (geo_name, "geo_names"), (genre_form, "genre_forms"),
        (creator, "creator_names"), (corp_name, "corp_names"), (pers_name, "pers_names"),
    ] if val]
    filters = build_filters(
        level=level, level_excl=level_excl,
        date_from=date_from, date_to=date_to,
        lang=lang,
        subject_norm=subject_norm, subject_norm_excl=subject_norm_excl,
        geo_name_norm=geo_name_norm, geo_name_norm_excl=geo_name_norm_excl,
        genre_form_norm=genre_form_norm, genre_form_norm_excl=genre_form_norm_excl,
        gff_norm=gff_norm, gff_norm_excl=gff_norm_excl,
        tdd_norm=tdd_norm, tdd_norm_excl=tdd_norm_excl,
        technique_norm=technique_norm, technique_norm_excl=technique_norm_excl,
        corp_name_norm=corp_name_norm,
        repository_id=repository_id, repository=repository, repository_excl=repository_excl,
        century=century, century_excl=century_excl,
    )
    if nl_filters:
        try:
            filters = filters + parse_nl_filters(_json.loads(nl_filters))
        except Exception:
            pass

    result = _search(
        query=build_query(q, field_terms, filters),
        size=n,
        aggs=facet_aggs(["repository", "level", "century", "subjects_norm", "geo_names_norm",
                         "genre_forms_norm", "corp_names_norm", "languages"]),
        source_includes=[
            "title", "unitid", "date_display", "date_normal", "repository",
            "level", "abstract", "scope_content", "biography",
            "subjects", "geo_names", "pers_names", "corp_names", "genre_forms",
            "creator_names", "languages", "phys_facets",
        ],
    )
    hits = hits_of(result)
    facets = facet_distribution(result)
    total = total_of(result)
    q_label = " ".join(filter(None, [q] + [val for _, val in field_terms]))

    def _fmt_facet(label: str, dist: dict, top: int = 8) -> str:
        if not dist:
            return ""
        top_vals = sorted(dist.items(), key=lambda x: -x[1])[:top]
        return f"{label} : " + ", ".join(f"{v} ({c})" for v, c in top_vals)

    facet_lines = [
        _fmt_facet("Institutions",      facets.get("repository", {})),
        _fmt_facet("Siècles",           facets.get("century", {}), 10),
        _fmt_facet("Sujets",            facets.get("subjects_norm", {})),
        _fmt_facet("Types de documents",facets.get("genre_forms_norm", {})),
        _fmt_facet("Niveaux",           facets.get("level", {})),
        _fmt_facet("Lieux",             facets.get("geo_names_norm", {})),
        _fmt_facet("Collectivités",     facets.get("corp_names_norm", {})),
        _fmt_facet("Langues",           facets.get("languages", {})),
    ]
    facet_block = "\n".join(line for line in facet_lines if line)

    def _fmt_hit(i: int, h: dict) -> str:
        lines = [f"[{i}] {h.get('title', '(sans titre)')}"]
        if h.get("unitid"):        lines.append(f"    Cote : {h['unitid']}")
        if h.get("repository"):    lines.append(f"    Institution : {h['repository']}")
        if h.get("date_display"):  lines.append(f"    Date : {h['date_display']}")
        if h.get("level"):         lines.append(f"    Niveau : {h['level']}")
        desc = h.get("abstract") or h.get("scope_content") or h.get("biography") or ""
        if desc:                   lines.append(f"    Description : {desc[:300]}")
        if h.get("subjects"):      lines.append(f"    Sujets : {', '.join(h['subjects'][:6])}")
        if h.get("pers_names"):    lines.append(f"    Personnes : {', '.join(h['pers_names'][:4])}")
        if h.get("geo_names"):     lines.append(f"    Lieux : {', '.join(h['geo_names'][:4])}")
        if h.get("genre_forms"):   lines.append(f"    Genre/forme : {', '.join(h['genre_forms'][:4])}")
        if h.get("creator_names"): lines.append(f"    Créateurs : {', '.join(h['creator_names'][:3])}")
        return "\n".join(lines)

    hits_block = "\n\n".join(_fmt_hit(i + 1, h) for i, h in enumerate(hits))
    user_content = (
        f"Requête : « {q_label or '(tous les documents)'} »\n"
        f"Nombre total de résultats : {total}\n\n"
        f"STATISTIQUES GLOBALES (facettes sur l'ensemble des résultats) :\n{facet_block}\n\n"
        f"DÉTAIL DES {len(hits)} PREMIERS RÉSULTATS :\n{hits_block}"
    )

    summary = f"({NOT_CONFIGURED})"
    if llm.enabled:
        try:
            import json as _json
            raw = call_llm(llm, load_summarize_prompt(), user_content, max_tokens=600, temperature=0.3)
            summary = _json.loads(raw).get("summary", "")
        except Exception as exc:
            summary = f"(erreur LLM : {exc})"

    return {
        "query":    q_label,
        "total":    total,
        "analyzed": len(hits),
        "summary":  summary,
    }


@app.get("/llm/check", summary="Vérifie la configuration du LLM")
def llm_check(llm: LLMConfig = Depends(_llm)) -> dict[str, Any]:
    """Envoie une requête minimale au LLM configuré (en-têtes X-LLM-*, à défaut serveur)."""
    info = {"source": llm.source, "base_url": llm.base_url, "model": llm.model}
    if not llm.enabled:
        return {**info, "ok": False, "error": NOT_CONFIGURED}
    try:
        call_llm(llm, 'Réponds uniquement par le JSON {"ok": true}.', "test", max_tokens=20)
    except Exception as exc:
        return {**info, "ok": False, "error": str(exc)}
    return {**info, "ok": True, "error": None}


@app.get("/person", summary="Get components for a person")
def get_person(
    name: Optional[str] = Query(default=None, description="Person name (exact)"),
    idref_id: Optional[str] = Query(default=None, description="IdRef identifier"),
    role: Optional[str] = Query(default=None, description="Filter by role"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """
    Return all components where a given person appears, with available roles as facets.
    Accepts either name or idref_id (idref_id resolved to name via the pers_name_ids values).
    """
    if idref_id and not name:
        probe = _search(
            query={"term": {"idref_ids": idref_id}},
            size=0,
            aggs=facet_aggs(["pers_name_ids"], 1000),
        )
        for key in facet_distribution(probe).get("pers_name_ids", {}):
            if f"||{idref_id}" in key:
                name = key.split("||")[0]
                break
        if not name:
            raise HTTPException(status_code=404, detail="Person not found")
    elif not name:
        raise HTTPException(status_code=400, detail="name or idref_id required")

    if role:
        filter_expr = {"term": {"pers_name_roles": f"{name}::{role}"}}
    else:
        filter_expr = {"term": {"pers_names.kw": name}}

    result = _search(
        query={"bool": {"filter": [filter_expr]}},
        size=limit,
        from_=offset,
        sort=[{"date_start": {"order": "asc", "missing": "_last"}}],
        aggs={
            "pers_name_roles": {"terms": {"field": "pers_name_roles", "size": 200,
                                          "include": _regexp_escape(name) + "(::.*)?"}},
            "pers_name_ids":   {"terms": {"field": "pers_name_ids", "size": 50,
                                          "include": _regexp_escape(name + "||") + ".*"}},
        },
    )

    hits = hits_of(result)
    total = total_of(result)
    facets = facet_distribution(result)

    pr_dist = facets.get("pers_name_roles", {})
    prefix = f"{name}::"
    roles = sorted(
        [{"role": k[len(prefix):], "count": v} for k, v in pr_dist.items() if k.startswith(prefix)],
        key=lambda r: -r["count"],
    )
    no_role_count = pr_dist.get(name, 0)
    if no_role_count:
        roles.append({"role": "", "count": no_role_count})

    # Retrieve IdRef ID from the pers_name_ids facet ("name||id" format).
    id_prefix = f"{name}||"
    resolved_idref: Optional[str] = None
    for key in facets.get("pers_name_ids", {}):
        if key.startswith(id_prefix):
            resolved_idref = key[len(id_prefix):]
            break

    return {
        "name":     name,
        "idref_id": resolved_idref,
        "roles":    roles,
        "total":    total,
        "offset":   offset,
        "limit":    limit,
        "hits":     hits,
    }
