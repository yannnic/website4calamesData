"""
Hierarchical grouping of search results, computed by Elasticsearch over the
whole result set (not only the first hits).

A parent component is *promoted* — shown instead of its matching descendants —
when its direct children that match the query, or were promoted themselves,
satisfy the rule of the chosen mode:

  coverage : at least COVERAGE_THRESHOLD of its children        (default)
  siblings : at least SIBLING_THRESHOLD children (règle des N frères)

Promotion is applied bottom-up until stable. The result list is then made of
the outermost promoted components and of the matching components outside
them. A promoted component scores as its best matching descendant, so the list
is ranked, counted and paginated by Elasticsearch like any other search.

Requests per search: one aggregation pass over the matches (more pages only for
very large result sets), one lookup per promotion level, the final page, and a
count of the matching descendants of the promoted components on that page.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from .filters import facet_distribution, hits_of, total_of

SIBLING_THRESHOLD  = int(os.getenv("SIBLING_THRESHOLD", "3"))
# Fraction of a parent's children that must match to trigger coverage grouping.
COVERAGE_THRESHOLD = float(os.getenv("COVERAGE_THRESHOLD", "0.75"))

COMPOSITE_PAGE = 10000
# Promoted components are fetched by id; beyond this, grouping stops early.
MAX_PROMOTED   = 10000

Search = Callable[..., Any]


def _rule(mode: str) -> Callable[[int, int], bool]:
    if mode == "siblings":
        return lambda n, _children: n >= SIBLING_THRESHOLD
    return lambda n, children: children > 0 and n / children >= COVERAGE_THRESHOLD


def _parent_stats(search: Search, query: dict, aggs: dict) -> tuple[Any, dict[str, list]]:
    """
    One pass over every matching component, grouped by parent:
    {parent_id: [matching children, parent's children count, best child score]}.
    The first response also carries `aggs` (facets) and the total hit count.
    """
    stats: dict[str, list] = {}
    first = None
    after = None
    while True:
        composite: dict[str, Any] = {"size": COMPOSITE_PAGE,
                                     "sources": [{"p": {"terms": {"field": "parent_id"}}}]}
        if after:
            composite["after"] = after
        page_aggs: dict[str, Any] = {"parents": {"composite": composite, "aggs": {
            "children": {"max": {"field": "parent_children_count"}},
            "best":     {"max": {"script": "_score"}},
        }}}
        if first is None:
            page_aggs.update(aggs)
        resp = search(query=query, size=0, aggs=page_aggs)
        first = first or resp
        agg = resp["aggregations"]["parents"]
        for b in agg["buckets"]:
            stats[b["key"]["p"]] = [b["doc_count"], int(b["children"]["value"] or 0),
                                    b["best"]["value"] or 0.0]
        after = agg.get("after_key")
        if len(agg["buckets"]) < COMPOSITE_PAGE or not after:
            return first, stats


def _promote(search: Search, query: dict, stats: dict[str, list],
             rule: Callable[[int, int], bool]) -> dict[str, dict]:
    """Bottom-up promotion. Returns {node_id: {"score", "parent_id", "ancestor_ids"}}."""
    promoted: dict[str, dict] = {}
    candidates = [p for p, (n, children, _) in stats.items() if rule(n, children)]
    while candidates:
        ids = candidates[:MAX_PROMOTED - len(promoted)]
        if len(ids) < len(candidates):
            print(f"[grouping] more than {MAX_PROMOTED} promoted components, grouping truncated")
        if not ids:
            break
        # The score is the component's own score for the query (0 if it does not match).
        resp = search(
            query={"bool": {"filter": [{"ids": {"values": ids}}], "should": [query]}},
            size=len(ids),
            source_includes=["node_id", "parent_id", "ancestor_ids", "parent_children_count"],
        )
        parents: set[str] = set()
        for h in resp["hits"]["hits"]:
            src = h["_source"]
            own = h["_score"] or 0.0
            promoted[src["node_id"]] = {
                "score": max(own, stats[src["node_id"]][2]),
                "parent_id": src.get("parent_id"),
                "ancestor_ids": src.get("ancestor_ids") or [],
            }
            pid = src.get("parent_id")
            if not pid:
                continue
            st = stats.setdefault(pid, [0, src.get("parent_children_count") or 0, 0.0])
            if own == 0:
                st[0] += 1  # a matching child is already counted
            parents.add(pid)
        candidates = [p for p in parents if p not in promoted and rule(*stats[p][:2])]

    # A promoted component scores as its best matching descendant: propagate upward.
    for nid in sorted(promoted, key=lambda n: -len(promoted[n]["ancestor_ids"])):
        pid = promoted[nid]["parent_id"]
        if pid in promoted:
            promoted[pid]["score"] = max(promoted[pid]["score"], promoted[nid]["score"])
    return promoted


def _grouped_query(query: dict, promoted: dict[str, dict], outer: list[str]) -> dict:
    """Matching components outside promoted subtrees + the outermost promoted components."""
    if not promoted:
        return query
    hidden = list(promoted)
    return {"bool": {"should": [
        {"bool": {"must": [query], "must_not": [
            {"terms": {"ancestor_ids": hidden}},
            {"ids": {"values": hidden}},
        ]}},
        {"script_score": {
            "query": {"ids": {"values": outer}},
            "script": {"source": "params.s[doc['node_id'].value]",
                       "params": {"s": {n: promoted[n]["score"] for n in outer}}},
        }},
    ], "minimum_should_match": 1}}


def grouped_search(search: Search, query: dict, mode: str, offset: int, limit: int,
                   aggs: dict) -> dict[str, Any]:
    """
    Run `query` with hierarchical grouping. Facets (`aggs`) and `total_hits` describe
    the matching components; `total` and `hits` describe the grouped list.
    Promoted hits carry `grouped_count`: their number of matching descendants.
    """
    first, stats = _parent_stats(search, query, aggs)
    promoted = _promote(search, query, stats, _rule(mode))
    outer = [n for n, p in promoted.items() if not any(a in promoted for a in p["ancestor_ids"])]

    resp = search(query=_grouped_query(query, promoted, outer), from_=offset, size=limit)
    hits = hits_of(resp)

    page_promoted = [h["node_id"] for h in hits if h["node_id"] in promoted]
    if page_promoted:
        counts = search(query=query, size=0, aggs={"g": {"terms": {
            "field": "ancestor_ids", "include": page_promoted, "size": len(page_promoted),
        }}})
        grouped = facet_distribution(counts)["g"]
        for h in hits:
            if h["node_id"] in promoted:
                h["grouped_count"] = grouped.get(h["node_id"], 0)

    return {
        "hits":       hits,
        "total":      total_of(resp),
        "total_hits": total_of(first),
        "facets":     facet_distribution({"aggregations": {k: first["aggregations"][k] for k in aggs}}),
    }
