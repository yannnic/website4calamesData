"""
EAD 2002 parser.

Parses a single EAD file and returns a list of indexable components,
with inherited fields resolved from ancestors.

Each component is a flat dict ready to be pushed to Elasticsearch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lxml import etree

# ---------------------------------------------------------------------------
# EAD namespace
# ---------------------------------------------------------------------------

NS_EAD2002 = "urn:isbn:1-931666-22-9"

# Module-level tag builder, reset per file in parse_ead().
# Safe for sequential (non-concurrent) use.
_ns_prefix: str = f"{{{NS_EAD2002}}}"


def _tag(local: str) -> str:
    return f"{_ns_prefix}{local}"


def _set_namespace(ns: str) -> None:
    """Switch the module-level namespace prefix before parsing a file."""
    global _ns_prefix, _tag
    p = f"{{{ns}}}" if ns else ""
    _ns_prefix = p

    def _tag(local: str) -> str:  # noqa: F811
        return f"{p}{local}"


# ---------------------------------------------------------------------------
# Fields that are inherited from ancestor to descendant when absent
# ---------------------------------------------------------------------------

INHERITED_FIELDS = {
    "access_restrict",
    "use_restrict",
    "languages",
    "repository",
    "repository_id",
}

# Date fields are inherited as a group: if a component has no date_normal,
# all four date fields are filled from the nearest ancestor that has one.
DATE_FIELDS = ("date_display", "date_normal", "date_start", "date_end")

# These fields accumulate across levels: a child keeps its own values AND
# receives all ancestor values (deduplicated). Order: own values first,
# then ancestor additions.
CUMULATIVE_INHERITED_FIELDS = {
    "subjects",
    "geo_names",
    "genre_forms",
    "corp_names",
    "pers_names",
    "fam_names",
    "pers_name_roles",
    "pers_name_ids",      # "NormalName||authfilenumber" pour liens IdRef
    "subjects_norm",
    "geo_names_norm",
    "genre_forms_norm",
    "corp_names_norm",
    "fam_names_norm",
    "gff_norm",           # genreform[@type="genre"]
    "tdd_norm",           # genreform[@type="type_de_document"]
    "technique_norm",     # genreform[@type="technique"]
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Component:
    """One node in the EAD hierarchy (archdesc or <c> element)."""

    # Identity
    node_id: str                        # xml:id or generated
    ead_id: str                         # eadid of the parent file
    level: str                          # fonds / series / subseries / file / item
    depth: int                          # 0 = archdesc (fonds), 1 = direct children, …

    # Ancestry (used for inheritance resolution and navigation)
    parent_id: Optional[str]
    ancestor_ids: list[str]             # ordered from root to direct parent

    # Descriptive fields
    unitid: str
    title: str
    date_display: str                   # human-readable
    date_normal: str                    # ISO range, e.g. "1952/2018"
    date_start: Optional[int]
    date_end: Optional[int]

    abstract: str
    scope_content: str
    biography: str

    # Agents
    creators: list[dict]                # [{"name": …, "role": …, "type": "person"|"corp"}]

    # Controlled access — full-text (normal + literal)
    subjects: list[str]
    geo_names: list[str]
    genre_forms: list[str]
    corp_names: list[str]               # from controlaccess (not creators)
    pers_names: list[str]               # from controlaccess (not creators), forme normale
    fam_names: list[str]                # from controlaccess <famname>
    # Controlled access — facettes/filtres (normal uniquement)
    subjects_norm: list[str]
    geo_names_norm: list[str]
    genre_forms_norm: list[str]        # tous les genreform
    gff_norm: list[str]               # genreform[@type="genre"]
    tdd_norm: list[str]               # genreform[@type="type_de_document"]
    technique_norm: list[str]         # genreform[@type="technique"]
    corp_names_norm: list[str]
    fam_names_norm: list[str]
    pers_name_roles: list[str]          # "NormalName::role" pairs
    pers_name_ids: list[str]            # "NormalName||authfilenumber" pour liens IdRef

    # Physical description
    extents: list[str]
    phys_facets: list[str]
    phys_facet_types: list[str]          # valeurs de @type (facette de filtrage)

    # Conditions
    access_restrict: str
    use_restrict: str

    # Languages
    languages: list[str]               # langcode list

    # Repository
    repository: str
    repository_id: str          # authfilenumber de <repository><corpname>

    # Children (used during tree construction, not indexed)
    children: list["Component"] = field(default_factory=list, repr=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inner_text(el: Optional[etree._Element], skip_tags: tuple[str, ...] = ()) -> str:
    """Concatenate all text nodes inside an element recursively.

    Args:
        el: Element to extract text from.
        skip_tags: Local tag names (without namespace) whose subtree is skipped,
                   e.g. ("head",) to drop section titles.
    """
    if el is None:
        return ""
    skip_full = tuple(_tag(t) for t in skip_tags)
    parts = []
    if el.text:
        parts.append(el.text.strip())
    for child in el:
        if child.tag in skip_full:
            if child.tail:
                parts.append(child.tail.strip())
            continue
        parts.append(_inner_text(child, skip_tags))
        if child.tail:
            parts.append(child.tail.strip())
    return " ".join(p for p in parts if p)


def _parse_date_normal(normal: str) -> tuple[Optional[int], Optional[int]]:
    """
    Parse ISO date ranges like "1952/2018", "1952", "1952-06".
    Returns (start_year, end_year).
    """
    if not normal:
        return None, None
    parts = normal.split("/")
    def year(s: str) -> Optional[int]:
        m = re.match(r"(\d{4})", s)
        return int(m.group(1)) if m else None
    start = year(parts[0])
    end = year(parts[-1])
    return start, end


def _find(el: etree._Element, local: str) -> Optional[etree._Element]:
    return el.find(_tag(local))


def _findall(el: etree._Element, local: str) -> list[etree._Element]:
    return el.findall(_tag(local))


def _find_path(el: etree._Element, *locals: str) -> Optional[etree._Element]:
    cur = el
    for loc in locals:
        cur = _find(cur, loc)
        if cur is None:
            return None
    return cur


# ---------------------------------------------------------------------------
# DID extraction
# ---------------------------------------------------------------------------

def _parse_did(did: etree._Element) -> dict:
    """Extract all fields from a <did> element."""

    unitid_el = _find(did, "unitid")
    unitid = _inner_text(unitid_el)

    title_el = _find(did, "unittitle")
    title = _inner_text(title_el)

    date_el = _find(did, "unitdate")
    date_display = _inner_text(date_el) if date_el is not None else ""
    date_normal = (date_el.get("normal") or "") if date_el is not None else ""
    date_start, date_end = _parse_date_normal(date_normal)

    abstract_el = _find(did, "abstract")
    abstract = _inner_text(abstract_el)

    # Languages
    languages = [
        lang_el.get("langcode", "")
        for lang_el in _findall(did, "langmaterial")
        for lang_el in _findall(lang_el, "language")
    ]

    # Repository
    repo_el = _find_path(did, "repository", "corpname")
    repository = _inner_text(repo_el)
    repository_id = (repo_el.get("authfilenumber", "") if repo_el is not None else "").strip()

    # Physical description
    extents, phys_facets, phys_facet_types = [], [], []
    for physdesc in _findall(did, "physdesc"):
        for ext in _findall(physdesc, "extent"):
            t = _inner_text(ext)
            if t:
                extents.append(t)
        for pf in _findall(physdesc, "physfacet"):
            t = _inner_text(pf)
            if t:
                phys_facets.append(t)
            typ = pf.get("type", "").strip()
            if typ and typ not in phys_facet_types:
                phys_facet_types.append(typ)

    # Creators (origination)
    creators = []
    orig_pers_name_ids: list = []
    for orig in _findall(did, "origination"):
        for persname in _findall(orig, "persname"):
            name = _persname_text(persname)
            creators.append({
                "name": name,
                "role": persname.get("role", ""),
                "type": "person",
            })
            auth_id = persname.get("authfilenumber", "").strip()
            if auth_id and name and persname.get("source", "").lower() == "sudoc":
                orig_pers_name_ids.append(f"{name}||{auth_id}")
        for corpname in _findall(orig, "corpname"):
            creators.append({
                "name": _inner_text(corpname),
                "role": corpname.get("role", ""),
                "type": "corp",
            })

    return {
        "unitid": unitid,
        "title": title,
        "date_display": date_display,
        "date_normal": date_normal,
        "date_start": date_start,
        "date_end": date_end,
        "abstract": abstract,
        "languages": languages,
        "repository": repository,
        "repository_id": repository_id,
        "extents": extents,
        "phys_facets": phys_facets,
        "phys_facet_types": phys_facet_types,
        "creators": creators,
        "orig_pers_name_ids": orig_pers_name_ids,
    }


# ---------------------------------------------------------------------------
# Controlled access extraction
# ---------------------------------------------------------------------------

_INDEX_TERM_TAGS = {
    "subject":    "subjects",
    "geogname":   "geo_names",
    "genreform":  "genre_forms",
    "corpname":   "corp_names",
    "persname":   "pers_names",
    "famname":    "fam_names",
}

# Tags whose subtree we stop descending into (child components + creator block)
_STOP_DESCENT = {"c", "dsc", "origination"}


def _controlled_texts(el: etree._Element) -> list[str]:
    """Return both normal and literal text for full-text search (deduplicated)."""
    normal  = (el.get("normal") or "").strip()
    literal = _inner_text(el).strip()
    seen, result = set(), []
    for v in (normal, literal):
        if v and v not in seen:
            seen.add(v)
            result.append(v)
    return result


def _controlled_norm(el: etree._Element) -> str:
    """Return normal attribute if present, else inner text — for facets/filters."""
    normal = (el.get("normal") or "").strip()
    return normal if normal else _inner_text(el).strip()


def _persname_text(el: etree._Element) -> str:
    """Retourne la forme normale d'un <persname> si disponible, sinon le texte."""
    normal = (el.get("normal") or "").strip()
    if normal:
        # Supprimer les dates entre parenthèses pour la forme d'affichage courte
        # ex. "Gaudin, Jean-Claude (1939-2024)" → on garde tel quel (dates utiles)
        return normal
    return _inner_text(el).strip()


_GENREFORM_TYPE_BUCKETS = {
    "genre":              "gff_norm",
    "type_de_document":   "tdd_norm",
    "technique":          "technique_norm",
}


def _collect_controlaccess(node: etree._Element,
                            subjects: list, geo_names: list, genre_forms: list,
                            corp_names: list, pers_names: list, fam_names: list,
                            pers_name_roles: list, pers_name_ids: list,
                            subjects_norm: list, geo_names_norm: list,
                            genre_forms_norm: list, corp_names_norm: list,
                            fam_names_norm: list,
                            gff_norm: list, tdd_norm: list, technique_norm: list) -> None:
    """Recursively collect indexing terms within a component's own scope."""
    _buckets = {
        "subjects": subjects, "geo_names": geo_names, "genre_forms": genre_forms,
        "corp_names": corp_names, "pers_names": pers_names, "fam_names": fam_names,
    }
    _norm_buckets = {
        "subjects": subjects_norm, "geo_names": geo_names_norm,
        "genre_forms": genre_forms_norm, "corp_names": corp_names_norm,
        "fam_names": fam_names_norm,
        "gff_norm": gff_norm, "tdd_norm": tdd_norm, "technique_norm": technique_norm,
    }
    _typed_norm_buckets = {
        "gff_norm": gff_norm, "tdd_norm": tdd_norm, "technique_norm": technique_norm,
    }
    for child in node:
        if not isinstance(child.tag, str):  # skip comments, PIs
            continue
        local = child.tag.split("}", 1)[1] if "}" in child.tag else child.tag
        if local in _STOP_DESCENT:
            continue
        bucket_key = _INDEX_TERM_TAGS.get(local)
        if bucket_key:
            if local == "persname":
                t = _persname_text(child)
                if t:
                    pers_names.append(t)
                    role = child.get("role", "").strip()
                    pers_name_roles.append(f"{t}::{role}" if role else t)
                    auth_id = child.get("authfilenumber", "").strip()
                    if auth_id and child.get("source", "").lower() == "sudoc":
                        pers_name_ids.append(f"{t}||{auth_id}")
            elif local == "genreform":
                # Plein texte : toujours dans genre_forms
                for t in _controlled_texts(child):
                    genre_forms.append(t)
                n = _controlled_norm(child)
                if n:
                    genre_forms_norm.append(n)
                    # Facette typée selon @type
                    typ = child.get("type", "").strip()
                    typed_bucket = _GENREFORM_TYPE_BUCKETS.get(typ)
                    if typed_bucket:
                        _typed_norm_buckets[typed_bucket].append(n)
            else:
                # Plein texte : normal + littéral
                for t in _controlled_texts(child):
                    _buckets[bucket_key].append(t)
                # Facettes : normal uniquement
                n = _controlled_norm(child)
                if n and bucket_key in _norm_buckets:
                    _norm_buckets[bucket_key].append(n)
        else:
            _collect_controlaccess(child, subjects, geo_names, genre_forms,
                                   corp_names, pers_names, fam_names,
                                   pers_name_roles, pers_name_ids,
                                   subjects_norm, geo_names_norm, genre_forms_norm,
                                   corp_names_norm, fam_names_norm,
                                   gff_norm, tdd_norm, technique_norm)


def _dedup(lst: list) -> list:
    seen: set = set()
    result = []
    for v in lst:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result


def _parse_controlaccess(el: etree._Element) -> dict:
    """Extract indexing terms from <controlaccess> blocks in el's own scope
    (does not descend into child <c>/<dsc> elements)."""
    subjects: list = []
    geo_names: list = []
    genre_forms: list = []
    corp_names: list = []
    pers_names: list = []
    fam_names: list = []
    pers_name_roles: list = []
    pers_name_ids: list = []
    subjects_norm: list = []
    geo_names_norm: list = []
    genre_forms_norm: list = []
    corp_names_norm: list = []
    fam_names_norm: list = []
    gff_norm: list = []
    tdd_norm: list = []
    technique_norm: list = []
    _collect_controlaccess(el, subjects, geo_names, genre_forms, corp_names,
                           pers_names, fam_names, pers_name_roles, pers_name_ids,
                           subjects_norm, geo_names_norm, genre_forms_norm,
                           corp_names_norm, fam_names_norm,
                           gff_norm, tdd_norm, technique_norm)
    return {
        "subjects":         _dedup(subjects),
        "geo_names":        _dedup(geo_names),
        "genre_forms":      _dedup(genre_forms),
        "corp_names":       _dedup(corp_names),
        "pers_names":       _dedup(pers_names),
        "fam_names":        _dedup(fam_names),
        "pers_name_roles":  _dedup(pers_name_roles),
        "pers_name_ids":    _dedup(pers_name_ids),
        "subjects_norm":    _dedup(subjects_norm),
        "geo_names_norm":   _dedup(geo_names_norm),
        "genre_forms_norm": _dedup(genre_forms_norm),
        "corp_names_norm":  _dedup(corp_names_norm),
        "fam_names_norm":   _dedup(fam_names_norm),
        "gff_norm":         _dedup(gff_norm),
        "tdd_norm":         _dedup(tdd_norm),
        "technique_norm":   _dedup(technique_norm),
    }


# ---------------------------------------------------------------------------
# Narrative fields
# ---------------------------------------------------------------------------

def _parse_narrative(el: etree._Element) -> dict:
    """Extract scope/content, biography/history from direct children of el."""
    scope_parts = []
    for sc in _findall(el, "scopecontent"):
        scope_parts.append(_inner_text(sc, skip_tags=("head",)))
    scope_content = " ".join(scope_parts)

    bio_parts = []
    for bh in _findall(el, "bioghist"):
        bio_parts.append(_inner_text(bh, skip_tags=("head",)))
    biography = " ".join(bio_parts)

    return {"scope_content": scope_content, "biography": biography}


def _parse_conditions(el: etree._Element) -> dict:
    ar_el = _find(el, "accessrestrict")
    ur_el = _find(el, "userestrict")
    return {
        "access_restrict": _inner_text(ar_el, skip_tags=("head",)),
        "use_restrict": _inner_text(ur_el, skip_tags=("head",)),
    }


# ---------------------------------------------------------------------------
# Node ID
# ---------------------------------------------------------------------------

def _node_id(el: etree._Element, ead_id: str, fallback_index: list[int]) -> str:
    xml_id = el.get("{http://www.w3.org/XML/1998/namespace}id") or el.get("id")
    if xml_id:
        return f"{ead_id}#{xml_id}"
    fallback_index[0] += 1
    return f"{ead_id}#auto-{fallback_index[0]}"


# ---------------------------------------------------------------------------
# Recursive tree builder
# ---------------------------------------------------------------------------

def _build_component(
    el: etree._Element,
    ead_id: str,
    depth: int,
    parent_id: Optional[str],
    ancestor_ids: list[str],
    fallback_index: list[int],
) -> Component:

    level = el.get("level", "")
    node_id = _node_id(el, ead_id, fallback_index)

    did_el = _find(el, "did")
    did_data = _parse_did(did_el) if did_el is not None else {}

    narrative = _parse_narrative(el)
    conditions = _parse_conditions(el)
    access = _parse_controlaccess(el)

    # Fusionner les personnes de <origination> dans pers_names, pers_name_roles et pers_name_ids
    orig_pers_names = []
    orig_pers_roles = []
    for c in did_data.get("creators", []):
        if c["type"] == "person" and c["name"]:
            orig_pers_names.append(c["name"])
            role = c.get("role", "").strip()
            orig_pers_roles.append(f"{c['name']}::{role}" if role else c["name"])
    access["pers_names"]      = _dedup(access.get("pers_names", []) + orig_pers_names)
    access["pers_name_roles"] = _dedup(access.get("pers_name_roles", []) + orig_pers_roles)
    access["pers_name_ids"]   = _dedup(access.get("pers_name_ids", []) + did_data.get("orig_pers_name_ids", []))

    comp = Component(
        node_id=node_id,
        ead_id=ead_id,
        level=level,
        depth=depth,
        parent_id=parent_id,
        ancestor_ids=list(ancestor_ids),
        unitid=did_data.get("unitid", ""),
        title=did_data.get("title", ""),
        date_display=did_data.get("date_display", ""),
        date_normal=did_data.get("date_normal", ""),
        date_start=did_data.get("date_start"),
        date_end=did_data.get("date_end"),
        abstract=did_data.get("abstract", ""),
        scope_content=narrative["scope_content"],
        biography=narrative["biography"],
        creators=did_data.get("creators", []),
        subjects=access["subjects"],
        geo_names=access["geo_names"],
        genre_forms=access["genre_forms"],
        corp_names=access["corp_names"],
        pers_names=access["pers_names"],
        fam_names=access["fam_names"],
        subjects_norm=access["subjects_norm"],
        geo_names_norm=access["geo_names_norm"],
        genre_forms_norm=access["genre_forms_norm"],
        gff_norm=access["gff_norm"],
        tdd_norm=access["tdd_norm"],
        technique_norm=access["technique_norm"],
        corp_names_norm=access["corp_names_norm"],
        fam_names_norm=access["fam_names_norm"],
        pers_name_roles=access.get("pers_name_roles", []),
        pers_name_ids=access.get("pers_name_ids", []),
        extents=did_data.get("extents", []),
        phys_facets=did_data.get("phys_facets", []),
        phys_facet_types=did_data.get("phys_facet_types", []),
        access_restrict=conditions["access_restrict"],
        use_restrict=conditions["use_restrict"],
        languages=did_data.get("languages", []),
        repository=did_data.get("repository", ""),
        repository_id=did_data.get("repository_id", ""),
    )

    # Recurse into <c> children: direct <c> children of el,
    # plus <c> children of any <dsc> directly under el.
    new_ancestors = ancestor_ids + [node_id]
    for direct in el:
        if direct.tag == _tag("c"):
            comp.children.append(
                _build_component(direct, ead_id, depth + 1, node_id, new_ancestors, fallback_index)
            )
        elif direct.tag == _tag("dsc"):
            for dsc_child in direct:
                if dsc_child.tag == _tag("c"):
                    comp.children.append(
                        _build_component(dsc_child, ead_id, depth + 1, node_id, new_ancestors, fallback_index)
                    )

    return comp


# ---------------------------------------------------------------------------
# Inheritance context (used only at indexing time, never mutates Component)
# ---------------------------------------------------------------------------

def _build_inherited_context(comp: Component, parent_ctx: dict) -> dict:
    ctx = dict(parent_ctx)

    for field_name in INHERITED_FIELDS:
        val = getattr(comp, field_name)
        if val:
            ctx[field_name] = val

    if comp.date_normal:
        ctx["_date_group"] = {f: getattr(comp, f) for f in DATE_FIELDS}

    for field_name in CUMULATIVE_INHERITED_FIELDS:
        ancestor_items = ctx.get(f"_cumul_{field_name}", [])
        own = getattr(comp, field_name)
        seen = set(own)
        ctx[f"_cumul_{field_name}"] = list(own) + [v for v in ancestor_items if v not in seen]

    return ctx


def _apply_inheritance(comp: Component, ctx: dict) -> dict:
    resolved = {}

    for field_name in INHERITED_FIELDS:
        own = getattr(comp, field_name)
        resolved[field_name] = own if own else ctx.get(field_name, own)

    if comp.date_normal:
        for f in DATE_FIELDS:
            resolved[f] = getattr(comp, f)
    elif "_date_group" in ctx:
        for f in DATE_FIELDS:
            resolved[f] = ctx["_date_group"].get(f, getattr(comp, f))
    else:
        for f in DATE_FIELDS:
            resolved[f] = getattr(comp, f)

    for field_name in CUMULATIVE_INHERITED_FIELDS:
        ancestor_items = ctx.get(f"_cumul_{field_name}", [])
        own = getattr(comp, field_name)
        seen = set(own)
        resolved[field_name] = list(own) + [v for v in ancestor_items if v not in seen]

    return resolved


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _propagate_dates_up(comp: Component) -> None:
    """Bottom-up pass: assign a date range to components that have none,
    computed as min(date_start) / max(date_end) across all descendants."""
    for child in comp.children:
        _propagate_dates_up(child)

    if comp.date_normal:
        return

    starts = [c.date_start for c in comp.children if c.date_start is not None]
    ends   = [c.date_end   for c in comp.children if c.date_end   is not None]
    if not starts and not ends:
        return

    date_start = min(starts) if starts else None
    date_end   = max(ends)   if ends   else None

    comp.date_start = date_start
    comp.date_end   = date_end
    comp.date_normal = (
        f"{date_start}/{date_end}" if date_start and date_end
        else str(date_start or date_end)
    )
    comp.date_display = (
        f"{date_start} – {date_end}" if date_start and date_end
        else str(date_start or date_end)
    )


def parse_ead(path: Path) -> Component:
    """
    Parse an EAD file and return the root Component (archdesc level) with its
    full children tree attached. Component values are raw EAD data — no
    inheritance is applied here. Use components_to_docs() to produce index
    documents with inheritance resolved.
    """
    tree = etree.parse(str(path), parser=etree.XMLParser(
        load_dtd=False,
        no_network=True,
        resolve_entities=False,
    ))
    root = tree.getroot()

    # Detect namespace from root element and configure module-level _tag
    ns = root.nsmap.get(None, "")  # default namespace
    _set_namespace(ns)

    eadid_el = root.find(f".//{_tag('eadid')}")
    ead_id = (_inner_text(eadid_el) if eadid_el is not None else path.stem).strip()

    publisher_el = root.find(f".//{_tag('publisher')}")
    publisher = _inner_text(publisher_el)

    archdesc = root.find(_tag("archdesc"))
    if archdesc is None:
        raise ValueError(f"No <archdesc> found in {path}")

    fallback_index = [0]
    root_comp = _build_component(
        archdesc, ead_id, depth=0, parent_id=None,
        ancestor_ids=[], fallback_index=fallback_index,
    )

    if not root_comp.repository and publisher:
        root_comp.repository = publisher

    _propagate_dates_up(root_comp)

    return root_comp


# ---------------------------------------------------------------------------
# Component tree -> Elasticsearch documents (inheritance applied here only)
# ---------------------------------------------------------------------------

_CENTURY_LABELS = {
    1: "Ier s.", 2: "IIe s.", 3: "IIIe s.", 4: "IVe s.", 5: "Ve s.",
    6: "VIe s.", 7: "VIIe s.", 8: "VIIIe s.", 9: "IXe s.", 10: "Xe s.",
    11: "XIe s.", 12: "XIIe s.", 13: "XIIIe s.", 14: "XIVe s.", 15: "XVe s.",
    16: "XVIe s.", 17: "XVIIe s.", 18: "XVIIIe s.", 19: "XIXe s.",
    20: "XXe s.", 21: "XXIe s.",
}


def _century_label(year: Optional[int]) -> Optional[str]:
    if year is None:
        return None
    c = year // 100 + (1 if year % 100 > 0 else 0)
    return _CENTURY_LABELS.get(c, f"{c}e s.")


@dataclass
class Anchor:
    """
    Attachment point of an EAD file under the root of its parent file
    (Calames liaisons, see liaisons.py). Built from the parent root's document.
    """
    node_id: str
    depth: int
    ancestor_ids: list[str]       # down to and including node_id
    ancestor_titles: list[str]    # down to and including the root's title
    ead_ids: list[str]            # the parent file and the files containing it
    ctx: dict                     # inherited context passed to the attached root
    children_count: int           # own children + attached files
    own_children_count: int       # attached files are positioned after these

    @classmethod
    def from_doc(cls, doc: dict) -> "Anchor":
        # The resolved fields of a document are exactly the context its
        # children inherit (see _build_inherited_context).
        ctx = {f: doc[f] for f in INHERITED_FIELDS if doc.get(f)}
        if doc.get("date_normal"):
            ctx["_date_group"] = {f: doc.get(f) for f in DATE_FIELDS}
        for f in CUMULATIVE_INHERITED_FIELDS:
            ctx[f"_cumul_{f}"] = list(doc.get(f) or [])
        return cls(
            node_id=doc["node_id"],
            depth=doc["depth"],
            ancestor_ids=list(doc.get("ancestor_ids") or []) + [doc["node_id"]],
            ancestor_titles=list(doc.get("ancestor_titles") or []) + [doc.get("title", "")],
            ead_ids=list(doc.get("ead_ids") or [doc["ead_id"]]),
            ctx=ctx,
            children_count=doc.get("children_count") or 0,
            own_children_count=doc.get("own_children_count", doc.get("children_count") or 0),
        )


def _rebase(comp: Component, anchor: Anchor) -> None:
    """Move a file's component tree under the anchor (depths and ancestry)."""
    comp.depth += anchor.depth + 1
    comp.ancestor_ids = anchor.ancestor_ids + comp.ancestor_ids
    if comp.parent_id is None:
        comp.parent_id = anchor.node_id
    for child in comp.children:
        _rebase(child, anchor)


def _comp_to_doc(comp: Component, resolved: dict, position: int = 0,
                 ancestor_titles: list[str] | None = None, parent_children_count: int = 0) -> dict:
    """Build one Elasticsearch document from a Component and its resolved fields."""
    return {
        "id": re.sub(r"[^a-zA-Z0-9_-]", "_", comp.node_id),
        "position": position,
        "node_id": comp.node_id,
        "ead_id": comp.ead_id,
        "level": comp.level,
        "depth": comp.depth,
        "parent_id": comp.parent_id,
        "ancestor_ids": comp.ancestor_ids,
        "unitid": comp.unitid,
        "title": comp.title,
        "date_display": resolved["date_display"],
        "date_normal": resolved["date_normal"],
        "date_start": resolved["date_start"],
        "date_end": resolved["date_end"],
        "abstract": comp.abstract,
        "scope_content": comp.scope_content,
        "biography": comp.biography,
        "creators": comp.creators,
        "creator_names": [c["name"] for c in comp.creators],
        "subjects": resolved["subjects"],
        "geo_names": resolved["geo_names"],
        "genre_forms": resolved["genre_forms"],
        "corp_names": resolved["corp_names"],
        "pers_names": resolved["pers_names"],
        "fam_names":  resolved["fam_names"],
        "subjects_norm": resolved["subjects_norm"],
        "geo_names_norm": resolved["geo_names_norm"],
        "genre_forms_norm": resolved["genre_forms_norm"],
        "gff_norm":         resolved["gff_norm"],
        "tdd_norm":         resolved["tdd_norm"],
        "technique_norm":   resolved["technique_norm"],
        "corp_names_norm": resolved["corp_names_norm"],
        "fam_names_norm":  resolved["fam_names_norm"],
        "pers_name_roles":  resolved["pers_name_roles"],
        "pers_name_ids":    resolved["pers_name_ids"],
        "idref_ids":        list({e.split("||")[1] for e in resolved["pers_name_ids"] if "||" in e}),
        "extents": comp.extents,
        "phys_facets": comp.phys_facets,
        "phys_facet_types": comp.phys_facet_types,
        "access_restrict": resolved["access_restrict"],
        "use_restrict": resolved["use_restrict"],
        "languages": resolved["languages"],
        "repository": resolved["repository"],
        "repository_id": resolved["repository_id"],
        "century": _century_label(resolved["date_start"]),
        "children_count": len(comp.children),
        # Children count of the parent: lets search-time grouping compute coverage
        # ratios from the children alone.
        "parent_children_count": parent_children_count,
        "ancestor_titles": list(ancestor_titles) if ancestor_titles else [],
    }


def _walk_and_index(comp: Component, parent_ctx: dict, docs: list[dict],
                    position: int = 0, ancestor_titles: list[str] | None = None,
                    parent_children_count: int = 0) -> None:
    if ancestor_titles is None:
        ancestor_titles = []
    ctx = _build_inherited_context(comp, parent_ctx)
    resolved = _apply_inheritance(comp, parent_ctx)
    docs.append(_comp_to_doc(comp, resolved, position, ancestor_titles, parent_children_count))
    child_ancestor_titles = ancestor_titles + [comp.title]
    for i, child in enumerate(comp.children):
        _walk_and_index(child, ctx, docs, position=i, ancestor_titles=child_ancestor_titles,
                        parent_children_count=len(comp.children))


def components_to_docs(root: Component, anchor: Anchor | None = None,
                       position: int = 0, attached_count: int = 0) -> list[dict]:
    """
    Walk the component tree rooted at root and return a flat list of
    Elasticsearch documents with inheritance fully resolved. The root document
    comes first.

    With an anchor, the file is attached under its parent file's root, at
    `position` among the anchor's children, and inherits from it.
    `attached_count` is the number of files attached under this file's root:
    they count as children of the root.
    """
    if anchor is not None:
        _rebase(root, anchor)
    docs: list[dict] = []
    _walk_and_index(
        root, anchor.ctx if anchor else {}, docs, position=position,
        ancestor_titles=anchor.ancestor_titles if anchor else None,
        parent_children_count=anchor.children_count if anchor else 0,
    )
    ead_ids = (anchor.ead_ids if anchor else []) + [root.ead_id]
    for doc in docs:
        doc["file_root"] = False
        doc["ead_ids"] = ead_ids
    root_doc = docs[0]
    root_doc["file_root"] = True
    root_doc["own_children_count"] = len(root.children)
    root_doc["children_count"] = len(root.children) + attached_count
    # The root's own children see the attached files as siblings.
    if attached_count:
        for doc in docs[1:]:
            if doc["parent_id"] == root.node_id:
                doc["parent_children_count"] = root_doc["children_count"]
    return docs
