"""
Smart pruning and sibling-grouping for search hit lists.

Both strategies promote child documents toward their parents in order to return
a concise, representative set of results rather than a flood of low-level items.

  apply_sibling_grouping — explicit grouping when N siblings share a parent
  apply_smart_pruning    — two-pass: coverage rule then ranking-score rule
"""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Callable

SIBLING_THRESHOLD  = int(os.getenv("SIBLING_THRESHOLD", "3"))
# Fraction of a parent's children that must appear to trigger coverage grouping.
COVERAGE_THRESHOLD = float(os.getenv("COVERAGE_THRESHOLD", "0.75"))


def apply_sibling_grouping(
    hits: list[dict],
    threshold: int,
    get_by_id: Callable[[str], dict],
) -> list[dict]:
    """
    Replace sibling groups with their parent when the group is large enough.

    Iterates until stable: each pass replaces groups of >= `threshold` siblings
    with their shared parent, then strips descendants whose ancestor is present.
    """
    changed = True
    while changed:
        changed = False
        groups: dict[str, list[dict]] = defaultdict(list)
        parentless: list[dict] = []

        for hit in hits:
            pid = hit.get("parent_id")
            if pid:
                groups[pid].append(hit)
            else:
                parentless.append(hit)

        new_hits = list(parentless)
        for pid, siblings in groups.items():
            if len(siblings) >= threshold:
                try:
                    parent = get_by_id(pid)
                    if not any(h.get("node_id") == pid for h in new_hits):
                        new_hits.append(parent)
                    changed = True
                except Exception:
                    new_hits.extend(siblings)
            else:
                new_hits.extend(siblings)

        hits = new_hits

    # Remove any descendant whose ancestor is already in the list.
    present_ids = {h["node_id"] for h in hits}
    return [
        h for h in hits
        if not any(anc_id in present_ids for anc_id in h.get("ancestor_ids", []))
    ]


def apply_smart_pruning(
    hits: list[dict],
    get_by_id: Callable[[str], dict],
) -> list[dict]:
    """
    Two-pass pruning for full-text search results.

    Pass 1 — Coverage:
        If >= COVERAGE_THRESHOLD of a parent's direct children appear in the
        hit list, replace those children with their parent (iterative, bottom-up).

    Pass 2 — Score:
        For any (ancestor, descendant) pair both still present, keep whichever
        has the higher _rankingScore (relative ES score) and discard the other.
    """
    # --- Pass 1: coverage rule ---
    changed = True
    while changed:
        changed = False
        by_parent: dict[str, list[dict]] = defaultdict(list)
        for h in hits:
            pid = h.get("parent_id")
            if pid:
                by_parent[pid].append(h)

        hit_by_id = {h["node_id"]: h for h in hits}
        new_hits: list[dict] = []
        replaced: set[str] = set()

        for h in hits:
            if h["node_id"] in replaced:
                continue
            pid = h.get("parent_id")
            if not pid or pid not in by_parent:
                new_hits.append(h)
                continue

            siblings = by_parent[pid]
            parent_in_hits = hit_by_id.get(pid)
            if parent_in_hits is not None:
                total_children = parent_in_hits.get("children_count", 0)
            else:
                try:
                    parent_doc = get_by_id(pid)
                    total_children = parent_doc.get("children_count", 0)
                except Exception:
                    total_children = 0

            if total_children > 0 and len(siblings) / total_children >= COVERAGE_THRESHOLD:
                for sib in siblings:
                    replaced.add(sib["node_id"])
                if pid not in hit_by_id:
                    try:
                        parent_doc = get_by_id(pid)
                        new_hits.append(parent_doc)
                        hit_by_id[pid] = parent_doc
                    except Exception:
                        # Keep children rather than losing results entirely.
                        new_hits.extend(h for h in siblings if h["node_id"] not in replaced or True)
                changed = True
            else:
                new_hits.append(h)

        hits = [h for h in new_hits if h["node_id"] not in replaced]
        # Re-add any parent that was inserted into new_hits but filtered above.
        for h in new_hits:
            if h["node_id"] not in {x["node_id"] for x in hits}:
                hits.append(h)

    # --- Pass 2: score rule ---
    present = {h["node_id"]: h for h in hits}
    to_remove: set[str] = set()

    for h in hits:
        score = h.get("_rankingScore", 0.0)
        for anc_id in h.get("ancestor_ids", []):
            if anc_id in present:
                anc_score = present[anc_id].get("_rankingScore", 0.0)
                if score >= anc_score:
                    to_remove.add(anc_id)
                else:
                    to_remove.add(h["node_id"])

    return [h for h in hits if h["node_id"] not in to_remove]
