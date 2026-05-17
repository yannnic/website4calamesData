"""
EAD indexer — parse a directory of EAD files and push documents to MeiliSearch.

Usage:
    python indexer.py [EAD_DIR] [--host HOST] [--api-key KEY] [--index INDEX]

Defaults:
    EAD_DIR   : ../../data
    HOST      : http://localhost:7700
    API_KEY   : (empty — MeiliSearch default for local dev)
    INDEX     : ead_components
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import meilisearch

from ead_parser import parse_ead, components_to_docs

# ---------------------------------------------------------------------------
# MeiliSearch index settings
# ---------------------------------------------------------------------------

# Fields searched by default (full-text)
SEARCHABLE_ATTRIBUTES = [
    "title",
    "abstract",
    "scope_content",
    "biography",
    "unitid",
    "creator_names",
    "subjects",
    "geo_names",
    "genre_forms",
    "corp_names",
    "pers_names",
    "fam_names",
    "phys_facets",
    "phys_facet_types",
]

# Fields available for filtering (facets, date ranges, level…)
FILTERABLE_ATTRIBUTES = [
    "node_id",
    "ead_id",
    "level",
    "depth",
    "parent_id",
    "children_count",
    "ancestor_ids",
    "date_start",
    "date_end",
    "languages",
    "subjects_norm",
    "geo_names_norm",
    "genre_forms_norm",
    "gff_norm",
    "tdd_norm",
    "technique_norm",
    "corp_names_norm",
    "fam_names_norm",
    "creator_names",
    "pers_names",
    "pers_name_roles",
    "pers_name_ids",
    "idref_ids",
    "repository",
    "repository_id",
    "access_restrict",
    "century",
    "phys_facet_types",
]

# Fields available for sorting
SORTABLE_ATTRIBUTES = [
    "position",
    "date_start",
    "date_end",
    "title",
]

# Batch size for MeiliSearch document uploads
BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------

def configure_index(client: meilisearch.Client, index: meilisearch.index.Index) -> None:
    """Apply settings to the MeiliSearch index and wait for the tasks."""
    tasks = [
        index.update_searchable_attributes(SEARCHABLE_ATTRIBUTES),
        index.update_filterable_attributes(FILTERABLE_ATTRIBUTES),
        index.update_sortable_attributes(SORTABLE_ATTRIBUTES),
        index.update_typo_tolerance({
            "enabled": True,
            "minWordSizeForTypos": {
                "oneTypo": 7,
                "twoTypos": 11,
            },
        }),
        index.update_settings({"faceting": {"maxValuesPerFacet": 2000}}),
    ]
    for task in tasks:
        _wait_for_task(client, task.task_uid)
    print("  Index settings applied.")


def _wait_for_task(client: meilisearch.Client, task_uid: int, timeout: int = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = client.get_task(task_uid)
        if task.status in ("succeeded", "failed"):
            if task.status == "failed":
                raise RuntimeError(f"MeiliSearch task {task_uid} failed: {task.error}")
            return
        time.sleep(0.2)
    raise TimeoutError(f"MeiliSearch task {task_uid} did not complete within {timeout}s")


def index_directory(
    ead_dir: Path,
    host: str,
    api_key: str,
    index_name: str,
    shallow: bool = False,
    limit: int | None = None,
) -> None:
    import time as _time
    _start = _time.time()
    client = meilisearch.Client(host, api_key or None)

    # Supprime et recrée l'index pour un slate propre (plus rapide que delete_all_documents)
    try:
        task = client.delete_index(index_name)
        _wait_for_task(client, task.task_uid, timeout=120)
        print(f"Index '{index_name}' supprimé.")
    except meilisearch.errors.MeilisearchApiError:
        pass  # n'existait pas encore
    task = client.create_index(index_name, {"primaryKey": "id"})
    _wait_for_task(client, task.task_uid)
    index = client.get_index(index_name)
    print(f"Index '{index_name}' créé.")

    configure_index(client, index)

    ead_files = sorted(ead_dir.glob("*.xml") if shallow else ead_dir.rglob("*.xml"))
    if limit:
        ead_files = ead_files[:limit]
    if not ead_files:
        print(f"No .xml files found in {ead_dir}", file=sys.stderr)
        return

    total_docs = 0
    total_errors = 0
    last_task_uid = None
    n_files = len(ead_files)
    # Sync every SYNC_EVERY files to avoid MeiliSearch queue overload
    SYNC_EVERY = 100

    for file_idx, ead_file in enumerate(ead_files, 1):
        print(f"[{file_idx}/{n_files}] {ead_file.name}...", end=" ", flush=True)
        try:
            root = parse_ead(ead_file)
            docs = components_to_docs(root)
            for doc in docs:
                doc["source_file"] = ead_file.name
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            total_errors += 1
            continue

        # Fire batches without waiting (MeiliSearch queues them in order)
        for i in range(0, len(docs), BATCH_SIZE):
            batch = docs[i : i + BATCH_SIZE]
            task = index.add_documents(batch, primary_key="id")
            last_task_uid = task.task_uid

        total_docs += len(docs)
        print(f"{len(docs)} docs queued.", flush=True)

        # Periodically sync to avoid queuing too far ahead
        if last_task_uid and file_idx % SYNC_EVERY == 0:
            elapsed_so_far = _time.time() - _start
            print(f"  → Syncing at file {file_idx}… ({elapsed_so_far:.0f}s elapsed, {total_docs} docs so far)", flush=True)
            _wait_for_task(client, last_task_uid, timeout=300)
            # Quick search perf check
            t0 = _time.time()
            client.index(index_name).search("archives")
            print(f"  → Search latency: {(_time.time()-t0)*1000:.0f}ms", flush=True)

    # Final sync
    if last_task_uid:
        print("\nWaiting for MeiliSearch to finish indexing…", flush=True)
        _wait_for_task(client, last_task_uid, timeout=600)

    elapsed = _time.time() - _start
    print(f"\nDone. {total_docs} documents indexed from {n_files - total_errors} files "
          f"({total_errors} errors) in {elapsed:.1f}s ({elapsed/60:.1f}min).")

    # Final search perf check
    stats = client.index(index_name).get_stats()
    print(f"Total documents in index: {stats.number_of_documents}")
    for query in ["archives", "manuscrit", "Richelieu"]:
        t0 = _time.time()
        res = client.index(index_name).search(query, {"limit": 10})
        ms = (_time.time() - t0) * 1000
        print(f"  Search '{query}': {res['estimatedTotalHits']} hits, {ms:.0f}ms")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Index EAD files into MeiliSearch.")
    parser.add_argument(
        "ead_dir",
        nargs="?",
        default=str(Path(__file__).parent.parent.parent / "data"),
        help="Directory containing EAD XML files (default: ../../data)",
    )
    parser.add_argument("--host", default="http://localhost:7700", help="MeiliSearch host URL")
    parser.add_argument("--api-key", default="", help="MeiliSearch API key")
    parser.add_argument("--index", default="ead_components", help="MeiliSearch index name")
    parser.add_argument("--shallow", action="store_true", help="Only index files directly in EAD_DIR (no subdirectories)")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of files to index")

    args = parser.parse_args()

    ead_dir = Path(args.ead_dir)
    if not ead_dir.is_dir():
        print(f"Error: '{ead_dir}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    index_directory(
        ead_dir=ead_dir,
        host=args.host,
        api_key=args.api_key,
        index_name=args.index,
        shallow=args.shallow,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
