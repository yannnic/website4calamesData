"""Elasticsearch query helpers shared across endpoints."""

from __future__ import annotations

import re
from typing import Any

# Full-text fields searched by `q`, with their relative weight (see INDEXING.md,
# « Plein texte »): the component's own text and authorities first; what it
# inherits from its ancestors (authorities, titles, date) with a low weight.
OWN_AUTHORITIES = ["pers_names", "corp_names", "fam_names", "subjects", "geo_names", "genre_forms"]
SEARCH_FIELDS = [
    "title^4",
    "unitid^3",
    "creator_names^3",
    *[f"{f}_own^2" for f in OWN_AUTHORITIES],
    # own + inherited: an inherited value only reaches this low weight
    *[f"{f}^0.3" for f in OWN_AUTHORITIES],
    "abstract^1.5",
    "scope_content",
    "biography",
    "phys_facets",
    "phys_facet_types",
    "other_text^0.5",
    "date_display^0.5",
    "ancestor_titles^0.3",
]

# Without stemming: bonus when the query appears as such (exact words, in order).
EXACT_FIELDS = ["title.exact^3", *[f"{f}_own.exact^2" for f in OWN_AUTHORITIES]]

# "Quoted phrases" are matched without stemming nor stop words (all words, in order).
PHRASE_FIELDS = ["title.exact", "abstract.exact", "scope_content.exact", "biography.exact",
                 "other_text.exact", *[f"{f}_own.exact" for f in OWN_AUTHORITIES]]

# Cotes: "Ms 1234", "MS.1234" and "ms1234" are the same (analyzer "cote").
COTE_FIELD = "unitid.cote"

_PHRASE = re.compile(r'"([^"]+)"')

# Facets returned by the search endpoints (all keyword fields).
SEARCH_FACETS = ["repository", "level", "century", "subjects_norm", "geo_names_norm",
                 "genre_forms_norm", "gff_norm", "tdd_norm", "technique_norm", "corp_names_norm"]


def text_query(text: str, fields: list[str] = SEARCH_FIELDS) -> dict:
    """
    Every term must match (operator AND). Exact terms may be spread across fields
    (cross_fields); typo-tolerant matching (1 typo from 7 chars, 2 from 11) applies
    within a single field and ranks below exact matches.

    With the default fields (search across everything):
      - "quoted phrases" must appear as such, in one field;
      - bonus for exact words (no stemming) in the title or own authorities;
      - a cote typed in any form matches on its own (Ms 1234 = MS.1234 = ms1234).
    """
    full = fields is SEARCH_FIELDS
    phrases = _PHRASE.findall(text) if full else []
    words = _PHRASE.sub(" ", text).strip() if phrases else text
    should: list[dict] = []
    if words:
        should += [
            {"multi_match": {"query": words, "fields": fields, "type": "cross_fields",
                             "operator": "and", "boost": 2}},
            {"multi_match": {"query": words, "fields": fields, "type": "best_fields",
                             "operator": "and", "fuzziness": "AUTO:7,11", "prefix_length": 1}},
        ]
    if full:
        should.append({"match": {COTE_FIELD: {"query": _PHRASE.sub(r"\1", text),
                                              "operator": "and", "boost": 6}}})
    query: dict = {"bool": {"should": should, "minimum_should_match": 1}}
    if full and words:
        # An ancestor's title completes a query but cannot satisfy it alone: at least
        # one word must be found in the component itself (or in its authorities, own
        # or inherited). Otherwise every descendant of a matching level would match.
        query["bool"]["filter"] = [{"multi_match": {
            "query": words, "fields": [f for f in fields if not f.startswith("ancestor_titles")],
            "operator": "or", "fuzziness": "AUTO:7,11", "prefix_length": 1}}]
    if phrases:
        query["bool"]["must"] = [{"multi_match": {"query": ph, "fields": PHRASE_FIELDS, "type": "phrase"}}
                                 for ph in phrases]
        if not words:
            query["bool"]["minimum_should_match"] = 0
    if not full:
        return query
    # Exact-match bonus: optional, raises the score without filtering.
    return {"bool": {"must": [query], "should": [
        {"multi_match": {"query": _PHRASE.sub(r"\1", text), "fields": EXACT_FIELDS,
                         "type": "phrase", "boost": 2}},
    ]}}


def build_query(q: str, field_terms: list[tuple[str, str]], filters: list[dict]) -> dict:
    """`q` across all fields, each (field, text) pair restricted to its field, plus filters."""
    must = [text_query(q)] if q else []
    must += [text_query(text, [field]) for field, text in field_terms]
    return {"bool": {"must": must or [{"match_all": {}}], "filter": filters}}


def facet_aggs(fields: list[str], size: int = 100) -> dict:
    return {f: {"terms": {"field": f, "size": size}} for f in fields}


def facet_distribution(resp: Any) -> dict[str, dict[str, int]]:
    """Turn terms aggregations into {field: {value: count}}."""
    return {
        name: {b["key"]: b["doc_count"] for b in agg.get("buckets", [])}
        for name, agg in (resp.get("aggregations") or {}).items()
    }


def hits_of(resp: Any) -> list[dict]:
    """
    Return the _source of each hit. When the query is scored, `_rankingScore` holds
    the score relative to the best hit (0–1), as expected by pruning and the frontend.
    """
    max_score = resp["hits"].get("max_score")
    hits = []
    for h in resp["hits"]["hits"]:
        doc = dict(h["_source"])
        if max_score and h.get("_score") is not None:
            doc["_rankingScore"] = h["_score"] / max_score
        hits.append(doc)
    return hits


def total_of(resp: Any) -> int:
    return resp["hits"]["total"]["value"]


def _term(field: str, value: Any) -> dict:
    return {"term": {field: value}}


def _not(clause: dict) -> dict:
    return {"bool": {"must_not": [clause]}}


def build_filters(
    *,
    level: str | None = None,
    level_excl: str | None = None,
    ead_id: str | None = None,
    date_from: int | None = None,
    date_to: int | None = None,
    lang: str | None = None,
    pers_name_role: str | None = None,
    subject_norm: str | None = None,
    subject_norm_excl: str | None = None,
    geo_name_norm: str | None = None,
    geo_name_norm_excl: str | None = None,
    genre_form_norm: str | None = None,
    genre_form_norm_excl: str | None = None,
    gff_norm: str | None = None,
    gff_norm_excl: str | None = None,
    tdd_norm: str | None = None,
    tdd_norm_excl: str | None = None,
    technique_norm: str | None = None,
    technique_norm_excl: str | None = None,
    corp_name_norm: str | None = None,
    repository_id: str | None = None,
    repository: str | None = None,
    repository_excl: str | None = None,
    century: str | None = None,
    century_excl: str | None = None,
) -> list[dict]:
    """Build a list of Elasticsearch filter clauses from common search parameters."""
    f: list[dict] = []
    if level:                 f.append(_term("level", level))
    if level_excl:            f.append(_not(_term("level", level_excl)))
    # ead_ids: the file and the files containing it (liaisons), so that a
    # parent file also covers the files attached below it.
    if ead_id:                f.append(_term("ead_ids", ead_id))
    if date_from is not None: f.append({"range": {"date_end": {"gte": date_from}}})
    if date_to is not None:   f.append({"range": {"date_start": {"lte": date_to}}})
    if lang:                  f.append(_term("languages", lang))
    if pers_name_role:        f.append(_term("pers_name_roles", pers_name_role))
    if subject_norm:          f.append(_term("subjects_norm", subject_norm))
    if subject_norm_excl:     f.append(_not(_term("subjects_norm", subject_norm_excl)))
    if geo_name_norm:         f.append(_term("geo_names_norm", geo_name_norm))
    if geo_name_norm_excl:    f.append(_not(_term("geo_names_norm", geo_name_norm_excl)))
    if genre_form_norm:       f.append(_term("genre_forms_norm", genre_form_norm))
    if genre_form_norm_excl:  f.append(_not(_term("genre_forms_norm", genre_form_norm_excl)))
    if gff_norm:              f.append(_term("gff_norm", gff_norm))
    if gff_norm_excl:         f.append(_not(_term("gff_norm", gff_norm_excl)))
    if tdd_norm:              f.append(_term("tdd_norm", tdd_norm))
    if tdd_norm_excl:         f.append(_not(_term("tdd_norm", tdd_norm_excl)))
    if technique_norm:        f.append(_term("technique_norm", technique_norm))
    if technique_norm_excl:   f.append(_not(_term("technique_norm", technique_norm_excl)))
    if corp_name_norm:        f.append(_term("corp_names_norm", corp_name_norm))
    if repository_id:         f.append(_term("repository_id", repository_id))
    elif repository:          f.append(_term("repository", repository))
    elif repository_excl:     f.append(_not(_term("repository", repository_excl)))
    if century:               f.append(_term("century", century))
    if century_excl:          f.append(_not(_term("century", century_excl)))
    return f


# ---------------------------------------------------------------------------
# Textual filters produced by the LLM (/nlsearch), e.g.
#   'genre_forms_norm = "photographie"', 'date_end >= 1840 AND date_start <= 1860',
#   'NOT (level = "item")'
# ---------------------------------------------------------------------------

NL_FILTER_FIELDS = {
    "level", "ead_id", "date_start", "date_end", "languages", "century", "repository",
    "repository_id", "subjects_norm", "geo_names_norm", "genre_forms_norm", "gff_norm",
    "tdd_norm", "technique_norm", "corp_names_norm", "fam_names_norm",
}

_NL_COND = re.compile(
    r'^(?P<field>\w+)\s*(?P<op>!=|>=|<=|=|>|<)\s*'
    r'(?:"(?P<str>(?:[^"\\]|\\.)*)"|(?P<num>-?\d+))$'
)
_RANGE_OPS = {">=": "gte", "<=": "lte", ">": "gt", "<": "lt"}


def _parse_nl_condition(expr: str) -> dict:
    expr = expr.strip()
    negate = False
    m = re.match(r"^NOT\s*\((.*)\)$", expr) or re.match(r"^NOT\s+(.*)$", expr)
    if m:
        negate, expr = True, m.group(1).strip()
    m = _NL_COND.match(expr)
    if not m or m["field"] not in NL_FILTER_FIELDS:
        raise ValueError(f"unsupported filter: {expr!r}")
    field, op = m["field"], m["op"]
    value: Any = int(m["num"]) if m["num"] is not None else re.sub(r"\\(.)", r"\1", m["str"])
    if op in _RANGE_OPS:
        clause = {"range": {field: {_RANGE_OPS[op]: value}}}
    else:
        clause = _term(field, value)
        negate ^= op == "!="
    return _not(clause) if negate else clause


def parse_nl_filters(exprs: list[str]) -> list[dict]:
    """Translate LLM filter strings into ES clauses; unsupported ones are skipped."""
    clauses: list[dict] = []
    for expr in exprs:
        for part in re.split(r"\s+AND\s+(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", str(expr)):
            try:
                clauses.append(_parse_nl_condition(part))
            except ValueError as exc:
                print(f"[nlsearch] {exc}")
    return clauses
