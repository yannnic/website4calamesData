"""
Calames HTML — FastAPI backend.

Endpoints :
  GET /persons            Index des personnes avec identifiant IdRef/Sudoc
  GET /fonds              Liste de tous les instruments de recherche (niveau fonds)
  GET /fonds/{ead_id}     Composant racine d'un instrument de recherche
  GET /component          Un composant EAD (par node_id)
  GET /children           Enfants directs d'un composant
  GET /ancestors          Chaîne des ancêtres (fil d'Ariane)
  GET /raw                Fragment XML EAD brut d'un composant
  GET /search             Recherche plein texte avec pruning hiérarchique
  GET /nlsearch           Recherche en langage naturel (via LLM)
  GET /summarize          Résumé LLM des résultats d'une recherche
  GET /person             Composants associés à une personne

Dépendances : MeiliSearch (MEILI_HOST), LLM OpenAI-compatible (NL_LLM_*)
Variables d'environnement : voir README.md
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import meilisearch
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from lxml import etree

from .filters import build_filters, ms_escape
from .llm import (
    NL_LLM_API_KEY,
    NL_LLM_BASE_URL,
    NL_LLM_MODEL,
    call_llm,
    load_nl_prompt,
    load_summarize_prompt,
)
from .pruning import (
    SIBLING_THRESHOLD,
    apply_sibling_grouping,
    apply_smart_pruning,
)

# ---------------------------------------------------------------------------
# Configuration (environment variables with sensible defaults)
# ---------------------------------------------------------------------------

MEILI_HOST  = os.getenv("MEILI_HOST", "http://localhost:7700")
DATA_DIR    = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent.parent / "data" / "calames"))
MEILI_KEY   = os.getenv("MEILI_KEY", "")
MEILI_INDEX = os.getenv("MEILI_INDEX", "ead_components")


# ---------------------------------------------------------------------------
# MeiliSearch client (shared, initialised at startup)
# ---------------------------------------------------------------------------

_ms_client: meilisearch.Client
_ms_index: meilisearch.index.Index


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ms_client, _ms_index
    _ms_client = meilisearch.Client(MEILI_HOST, MEILI_KEY or None)
    _ms_index  = _ms_client.index(MEILI_INDEX)
    _prompt_dir = Path(__file__).parent
    try:
        # Pre-fetch facet values to generate a live NL prompt with real index data.
        res = _ms_index.search("", {"limit": 0, "facets": ["genre_forms_norm", "gff_norm", "tdd_norm", "technique_norm"]})
        dist = res.get("facetDistribution", {})

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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_by_id(node_id: str) -> dict:
    """Fetch a single document from MeiliSearch by node_id (not the MS id)."""
    result = _ms_index.search("", {
        "filter": f'node_id = "{ms_escape(node_id)}"',
        "limit": 1,
    })
    hits = result["hits"]
    if not hits:
        raise HTTPException(status_code=404, detail=f"Component not found: {node_id}")
    return hits[0]


def _get_by_ms_id(ms_id: str) -> dict:
    """Fetch a single document by its MeiliSearch id field (converts __ back to #)."""
    return _get_by_id(ms_id.replace("__", "#"))


def _norm_first_char(s: str) -> str:
    """Return the base (unaccented) uppercase first character of a string."""
    if not s:
        return ""
    import unicodedata
    first = unicodedata.normalize("NFD", s[0]).upper()
    return "".join(c for c in first if unicodedata.category(c) != "Mn")


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
    Results are sourced from the pers_name_ids facet ("Name||id" entries).
    Returns up to 500 persons + has_more flag for sub-level navigation.
    """
    LIMIT = 500
    facet_query = prefix or q or letter or ""

    result = _ms_index.facet_search("pers_name_ids", facet_query, {"limit": LIMIT})
    hits = result.get("facetHits", [])
    has_more = result.get("hasMore", False)

    # Strict letter filter (accent-aware): only when letter given without prefix/q.
    if letter and not prefix and not q:
        letter_up = letter.upper()
        hits = [h for h in hits if _norm_first_char(h["value"].split("||")[0]) == letter_up]

    # Parse "Name||idref_id" entries, deduplicate by name.
    seen: set[str] = set()
    persons = []
    for h in hits:
        v = h.get("value", "")
        if "||" not in v:
            continue
        name, idref_id = v.rsplit("||", 1)
        if name not in seen:
            seen.add(name)
            persons.append({"name": name, "idref_id": idref_id, "count": h["count"]})

    return {"persons": persons, "has_more": has_more}


@app.get("/fonds", summary="List all finding aids")
def list_fonds() -> list[dict]:
    """Return all fonds-level (root) components."""
    result = _ms_index.search("", {
        "filter": 'depth = 0',
        "limit": 1000,
        "attributesToRetrieve": [
            "node_id", "ead_id", "title", "unitid",
            "date_display", "date_normal", "date_start", "date_end",
            "repository", "repository_id", "creators", "abstract", "languages",
            "children_count",
        ],
    })
    return result["hits"]


@app.get("/fonds/{ead_id}", summary="Get root component of a finding aid")
def get_fonds(ead_id: str) -> dict:
    """Return the fonds-level component for a given EAD identifier."""
    result = _ms_index.search("", {
        "filter": [f'ead_id = "{ms_escape(ead_id)}"', 'depth = 0'],
        "limit": 1,
    })
    hits = result["hits"]
    if not hits:
        raise HTTPException(status_code=404, detail=f"Finding aid not found: {ead_id}")
    return hits[0]


@app.get("/component", summary="Get a single component")
def get_component(node_id: str = Query(..., description="Component node_id")) -> dict:
    return _get_by_id(node_id)


@app.get("/children", summary="Get direct children of a component")
def get_children(node_id: str = Query(..., description="Parent node_id")) -> list[dict]:
    """Return direct children of a component, in EAD document order."""
    result = _ms_index.search("", {
        "filter": f'parent_id = "{ms_escape(node_id)}"',
        "sort": ["position:asc"],
        "limit": 1000,
        "attributesToRetrieve": [
            "node_id", "ead_id", "level", "depth", "parent_id",
            "unitid", "title", "date_display", "date_normal",
            "date_start", "date_end", "extents", "access_restrict",
            "children_count",
        ],
    })
    return result["hits"]


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

    id_filter = " OR ".join(f'node_id = "{ms_escape(aid)}"' for aid in ancestor_ids)
    result = _ms_index.search("", {
        "filter": id_filter,
        "limit": len(ancestor_ids),
        "attributesToRetrieve": ["node_id", "level", "depth", "title", "unitid", "ead_id"],
    })
    hits = result["hits"]
    order = {aid: i for i, aid in enumerate(ancestor_ids)}
    hits.sort(key=lambda h: order.get(h["node_id"], 999))
    return hits


@app.get("/raw", summary="Raw EAD XML for a component", response_class=PlainTextResponse)
def get_raw(node_id: str = Query(..., description="Component node_id")) -> str:
    """Return the raw EAD XML fragment for a component."""
    doc = _get_by_id(node_id)
    source_file = doc.get("source_file")
    if not source_file:
        raise HTTPException(status_code=404, detail="Source file not recorded for this component (reindex needed)")

    ead_path = DATA_DIR / source_file
    if not ead_path.exists():
        ead_path = DATA_DIR.parent / source_file
    if not ead_path.exists():
        raise HTTPException(status_code=404, detail=f"EAD file not found: {source_file}")

    tree = etree.parse(str(ead_path), parser=etree.XMLParser(
        load_dtd=False, no_network=True, resolve_entities=False,
    ))
    root = tree.getroot()

    # node_id format: "{ead_id}#{component_id}"
    component_id = node_id.split("#", 1)[1] if "#" in node_id else ""

    if not component_id or component_id.startswith("auto-"):
        el = root.find(".//{urn:isbn:1-931666-22-9}archdesc") or root.find("archdesc")
    else:
        NS_XML = "http://www.w3.org/XML/1998/namespace"
        el = (root.find(f'.//*[@id="{component_id}"]')
              or root.find(f'.//*[@{{{NS_XML}}}id="{component_id}"]'))

    if el is None:
        raise HTTPException(status_code=404, detail=f"Element '{component_id}' not found in {source_file}")

    return etree.tostring(el, encoding="unicode", pretty_print=True)


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
    # Pagination & options
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sibling_grouping: bool = Query(default=False, description="Apply sibling-grouping rule"),
) -> dict[str, Any]:
    """
    Full-text search across all indexed EAD components.

    `q` is searched across title, abstract, scope/content, biography,
    unitid, creator names, subjects, geographic names, genre/forms,
    corporate names, personal names, and physical facets.

    Field-specific text params (subject, geo_name, …) are merged into `q` and,
    when used without a general `q`, restrict the searched attributes.

    Smart pruning: when results span multiple hierarchy levels and no `level`
    filter is active, child documents are promoted toward their parents to
    return a compact, representative result set.
    """
    filters = build_filters(
        level=level, level_excl=level_excl,
        ead_id=ead_id,
        date_from=date_from, date_to=date_to,
        lang=lang, pers_name_role=pers_name_role,
        subject_norm=subject_norm, subject_norm_excl=subject_norm_excl,
        geo_name_norm=geo_name_norm, geo_name_norm_excl=geo_name_norm_excl,
        genre_form_norm=genre_form_norm, genre_form_norm_excl=genre_form_norm_excl,
        corp_name_norm=corp_name_norm,
        repository_id=repository_id, repository=repository, repository_excl=repository_excl,
        century=century, century_excl=century_excl,
    )

    # Field-specific text terms: merged into the query, optionally restrict attributes.
    TEXT_FIELD_ATTRS: list[tuple[str | None, str]] = [
        (subject,    "subjects"),
        (geo_name,   "geo_names"),
        (genre_form, "genre_forms"),
        (creator,    "creator_names"),
        (corp_name,  "corp_names"),
        (pers_name,  "pers_names"),
    ]
    active_text = [(val, attr) for val, attr in TEXT_FIELD_ATTRS if val]
    combined_q = " ".join(filter(None, [q] + [val for val, _ in active_text]))

    # Restrict searched attributes only when field terms are used without a general query.
    attrs_to_search: list[str] | None = None
    if active_text and not q:
        attrs_to_search = [attr for _, attr in active_text]

    # Smart pruning needs a multi-level result set. With a level filter all results
    # are at the same depth, so pruning would be a no-op — use native MS pagination.
    needs_pruning = bool(combined_q) and not level
    local_pagination = sibling_grouping or needs_pruning

    ms_params: dict[str, Any] = {
        # Fetch a larger pool when we need to prune/group before paginating locally.
        "limit":            200 if local_pagination else limit,
        "offset":           0   if local_pagination else offset,
        "matchingStrategy": "all" if combined_q else "last",
        "showRankingScore": True,
        "facets": ["repository", "level", "century", "subjects_norm", "geo_names_norm", "genre_forms_norm", "corp_names_norm"],
    }
    if filters:
        ms_params["filter"] = filters
    if attrs_to_search:
        ms_params["attributesToSearchOn"] = attrs_to_search

    result = _ms_index.search(combined_q, ms_params)
    hits: list[dict] = result["hits"]
    facet_distribution: dict = result.get("facetDistribution", {})
    total_ms = result.get("estimatedTotalHits", len(hits))

    if sibling_grouping:
        hits = apply_sibling_grouping(hits, SIBLING_THRESHOLD, _get_by_id)
    elif needs_pruning:
        hits = apply_smart_pruning(hits, _get_by_id)

    total = len(hits)
    hits = hits[offset: offset + limit]

    return {
        "query":    q,
        "total":    total,
        "total_ms": total_ms,
        "offset":   offset,
        "limit":    limit,
        "hits":     hits,
        "facets":   facet_distribution,
    }


@app.get("/nlsearch", summary="Recherche en langage naturel")
async def nl_search(
    q: str = Query(..., description="Requête en langage naturel"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """
    Traduit une phrase en langage naturel en requête MeiliSearch via un LLM,
    puis exécute la recherche.

    Si NL_LLM_API_KEY est absent, effectue une recherche plein texte brute sur q.
    Le champ `interpreted` expose la traduction effectuée par le LLM.
    """
    interpreted: dict = {"q": q, "filters": [], "explanation": ""}

    if NL_LLM_API_KEY:
        try:
            import json as _json
            system = load_nl_prompt()
            print(f"\n[nlsearch] model={NL_LLM_MODEL} base_url={NL_LLM_BASE_URL}")
            print(f"[nlsearch] user: {q}")
            raw = call_llm(system, q, max_tokens=400, temperature=0)
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

    ms_params: dict[str, Any] = {
        "limit":            200,
        "offset":           0,
        "matchingStrategy": "all" if interpreted["q"] else "last",
        "showRankingScore": True,
        "facets": ["repository", "level", "century", "subjects_norm", "geo_names_norm", "genre_forms_norm"],
    }
    if interpreted["filters"]:
        ms_params["filter"] = interpreted["filters"]

    result = _ms_index.search(interpreted["q"], ms_params)
    hits: list[dict] = result["hits"]
    if interpreted["q"]:
        hits = apply_smart_pruning(hits, _get_by_id)

    total = len(hits)
    return {
        "natural_query": q,
        "interpreted":   interpreted,
        "total":         total,
        "offset":        offset,
        "limit":         limit,
        "hits":          hits[offset: offset + limit],
        "facets":        result.get("facetDistribution", {}),
    }


@app.get("/summarize", summary="Résumé LLM des résultats d'une recherche")
async def summarize_results(
    q: str = Query(default="", description="Requête de recherche"),
    n: int = Query(default=10, ge=1, le=50, description="Nombre de résultats à analyser en détail"),
    nl_filters: Optional[str] = Query(default=None, description="Filtres LLM (JSON array) issus de /nlsearch"),
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
    corp_name_norm: Optional[str] = Query(default=None),
    repository: Optional[str] = Query(default=None),
    repository_id: Optional[str] = Query(default=None),
    repository_excl: Optional[str] = Query(default=None),
    century: Optional[str] = Query(default=None),
    century_excl: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """
    Effectue la recherche, puis demande au LLM de synthétiser les résultats.
    Les facettes couvrent l'ensemble des résultats ; le détail porte sur les n premiers.
    En mode NL, passer nl_filters (JSON array de filtres MeiliSearch issus de /nlsearch).
    """
    import json as _json
    filters = build_filters(
        level=level, level_excl=level_excl,
        date_from=date_from, date_to=date_to,
        lang=lang,
        subject_norm=subject_norm, subject_norm_excl=subject_norm_excl,
        geo_name_norm=geo_name_norm, geo_name_norm_excl=geo_name_norm_excl,
        genre_form_norm=genre_form_norm, genre_form_norm_excl=genre_form_norm_excl,
        corp_name_norm=corp_name_norm,
        repository_id=repository_id, repository=repository, repository_excl=repository_excl,
        century=century, century_excl=century_excl,
    )
    if nl_filters:
        try:
            filters = filters + _json.loads(nl_filters)
        except Exception:
            pass

    ms_params: dict[str, Any] = {
        "limit": n,
        "offset": 0,
        "matchingStrategy": "all" if q else "last",
        "facets": ["repository", "level", "century", "subjects_norm", "geo_names_norm",
                   "genre_forms_norm", "corp_names_norm", "languages"],
        "attributesToRetrieve": [
            "title", "unitid", "date_display", "date_normal", "repository",
            "level", "abstract", "scope_content", "biography",
            "subjects", "geo_names", "pers_names", "corp_names", "genre_forms",
            "creator_names", "languages", "phys_facets",
        ],
    }
    if filters:
        ms_params["filter"] = filters

    result = _ms_index.search(q, ms_params)
    hits: list[dict] = result["hits"]
    facets: dict = result.get("facetDistribution", {})
    total: int = result.get("estimatedTotalHits", len(hits))

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
        f"Requête : « {q or '(tous les documents)'} »\n"
        f"Nombre total de résultats : {total}\n\n"
        f"STATISTIQUES GLOBALES (facettes sur l'ensemble des résultats) :\n{facet_block}\n\n"
        f"DÉTAIL DES {len(hits)} PREMIERS RÉSULTATS :\n{hits_block}"
    )

    summary = ""
    if NL_LLM_API_KEY:
        try:
            import json as _json
            raw = call_llm(load_summarize_prompt(), user_content, max_tokens=600, temperature=0.3)
            summary = _json.loads(raw).get("summary", "")
        except Exception as exc:
            summary = f"(erreur LLM : {exc})"

    return {
        "query":    q,
        "total":    total,
        "analyzed": len(hits),
        "summary":  summary,
    }


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
    Accepts either name or idref_id (idref_id resolved to name via facet lookup).
    """
    if idref_id and not name:
        probe = _ms_index.search("", {
            "filter": f'idref_ids = "{ms_escape(idref_id)}"',
            "facets": ["pers_name_ids"],
            "limit": 1,
        })
        for key in probe.get("facetDistribution", {}).get("pers_name_ids", {}):
            if f"||{idref_id}" in key:
                name = key.split("||")[0]
                break
        if not name:
            raise HTTPException(status_code=404, detail="Person not found")
    elif not name:
        raise HTTPException(status_code=400, detail="name or idref_id required")

    if role:
        filter_expr = f'pers_name_roles = "{ms_escape(name)}::{ms_escape(role)}"'
    else:
        filter_expr = f'pers_names = "{ms_escape(name)}"'

    result = _ms_index.search("", {
        "filter": filter_expr,
        "limit": limit,
        "offset": offset,
        "facets": ["pers_name_roles", "pers_name_ids"],
        "sort": ["date_start:asc"],
    })

    hits = result["hits"]
    total = result.get("estimatedTotalHits", len(hits))

    pr_dist = result.get("facetDistribution", {}).get("pers_name_roles", {})
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
    for key in result.get("facetDistribution", {}).get("pers_name_ids", {}):
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
