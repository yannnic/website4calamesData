"""
EAD indexer — parse a directory of EAD files and push documents to Elasticsearch.

Usage:
    python indexer.py [EAD_DIR] [--host HOST] [--user USER] [--password PWD] [--index INDEX]

Defaults:
    EAD_DIR   : ../../data
    HOST      : http://localhost:9200
    USER      : elastic (only used when a password is given)
    PASSWORD  : (empty — security disabled, local dev)
    INDEX     : ead_components
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Iterator

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from elasticsearch import Elasticsearch, NotFoundError, helpers

from ead_parser import parse_ead, components_to_docs

# ---------------------------------------------------------------------------
# Elasticsearch index settings & mapping
# ---------------------------------------------------------------------------

INDEX_SETTINGS = {
    # Single-node deployment: one shard, no replica (a replica would never be
    # allocated and the cluster would stay yellow).
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "max_result_window": 10000,
    "analysis": {
        "filter": {
            "fr_elision": {
                "type": "elision",
                "articles_case": True,
                "articles": ["l", "m", "t", "qu", "n", "s", "j", "d", "c",
                             "jusqu", "quoiqu", "lorsqu", "puisqu"],
            },
            "fr_stop": {"type": "stop", "stopwords": "_french_"},
            "fr_stemmer": {"type": "stemmer", "language": "light_french"},
        },
        "analyzer": {
            # Stop words are removed before folding: the French list contains accented forms.
            "fr_text": {
                "tokenizer": "standard",
                "filter": ["fr_elision", "lowercase", "fr_stop", "asciifolding", "fr_stemmer"],
            },
        },
    },
}

_TEXT    = {"type": "text", "analyzer": "fr_text"}
_TEXT_KW = {**_TEXT, "fields": {"kw": {"type": "keyword", "ignore_above": 1024}}}
_KW      = {"type": "keyword", "ignore_above": 1024}
_INT     = {"type": "integer"}

# Only the fields searched, filtered, aggregated or sorted on are mapped;
# everything else is kept in _source for display ("dynamic": false).
INDEX_MAPPINGS = {
    "dynamic": False,
    "properties": {
        # Full-text fields (fields with a .kw sub-field are also filtered exactly)
        "title":            _TEXT_KW,
        "abstract":         _TEXT,
        "scope_content":    _TEXT,
        "biography":        _TEXT,
        "unitid":           _TEXT_KW,
        "creator_names":    _TEXT_KW,
        "subjects":         _TEXT,
        "geo_names":        _TEXT,
        "genre_forms":      _TEXT,
        "corp_names":       _TEXT,
        "pers_names":       _TEXT_KW,
        "fam_names":        _TEXT,
        "phys_facets":      _TEXT,
        "phys_facet_types": _TEXT_KW,
        # Structure
        "id":               _KW,
        "node_id":          _KW,
        "ead_id":           _KW,
        "level":            _KW,
        "depth":            _INT,
        "parent_id":        _KW,
        "ancestor_ids":     _KW,
        "children_count":   _INT,
        "position":         _INT,
        "source_file":      _KW,
        # Dates
        "date_start":       _INT,
        "date_end":         _INT,
        "century":          _KW,
        # Facets / exact filters
        "languages":        _KW,
        "subjects_norm":    _KW,
        "geo_names_norm":   _KW,
        "genre_forms_norm": _KW,
        "gff_norm":         _KW,
        "tdd_norm":         _KW,
        "technique_norm":   _KW,
        "corp_names_norm":  _KW,
        "fam_names_norm":   _KW,
        "pers_name_roles":  _KW,
        "pers_name_ids":    _KW,
        "idref_ids":        _KW,
        "repository":       _KW,
        "repository_id":    _KW,
    },
}

# Batch size for bulk uploads
BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------

def make_client(host: str, user: str = "", password: str = "") -> Elasticsearch:
    """Build an Elasticsearch client (basic auth only when a password is given)."""
    auth = (user or "elastic", password) if password else None
    return Elasticsearch(host, basic_auth=auth, request_timeout=60)


def create_index(client: Elasticsearch, index_name: str) -> None:
    client.indices.create(index=index_name, settings=INDEX_SETTINGS, mappings=INDEX_MAPPINGS)
    print(f"Index '{index_name}' créé.")


def ensure_index(client: Elasticsearch, index_name: str) -> None:
    """Create the index if missing, otherwise push the (additive) mapping. Idempotent."""
    if not client.indices.exists(index=index_name):
        create_index(client, index_name)
        return
    # New fields can be added to an existing mapping; changing an existing field's
    # type or analyzer requires a full reindex (indexer.py).
    client.indices.put_mapping(index=index_name, **INDEX_MAPPINGS)


def _actions(index_name: str, docs: list[dict]) -> Iterator[dict]:
    for doc in docs:
        yield {"_index": index_name, "_id": doc["node_id"], "_source": doc}


def _bulk(client: Elasticsearch, index_name: str, docs: list[dict], refresh: bool | str = False) -> None:
    helpers.bulk(client, _actions(index_name, docs), chunk_size=BATCH_SIZE, refresh=refresh)


def index_file(client: Elasticsearch, index_name: str, ead_file: Path) -> int:
    """
    (Re)index a single EAD file: drop the documents previously produced by this
    file, then push the new ones. Returns the number of documents indexed.
    Raises on parse error (the previous documents are kept in that case).
    """
    root = parse_ead(ead_file)
    docs = components_to_docs(root)
    for doc in docs:
        doc["source_file"] = ead_file.name

    remove_file(client, index_name, ead_file.name)
    _bulk(client, index_name, docs, refresh="wait_for")
    return len(docs)


def remove_file(client: Elasticsearch, index_name: str, file_name: str) -> None:
    """Delete every document produced by a given source file."""
    client.delete_by_query(
        index=index_name,
        query={"term": {"source_file": file_name}},
        conflicts="proceed",
        refresh=True,
    )


def index_directory(
    ead_dir: Path,
    host: str,
    user: str,
    password: str,
    index_name: str,
    shallow: bool = False,
    limit: int | None = None,
) -> None:
    _start = time.time()
    client = make_client(host, user, password)

    # Supprime et recrée l'index pour un slate propre (mapping à jour)
    try:
        client.indices.delete(index=index_name)
        print(f"Index '{index_name}' supprimé.")
    except NotFoundError:
        pass  # n'existait pas encore
    create_index(client, index_name)
    # Pas de refresh pendant le chargement massif (rétabli à la fin)
    client.indices.put_settings(index=index_name, settings={"refresh_interval": "-1"})

    ead_files = sorted(ead_dir.glob("*.xml") if shallow else ead_dir.rglob("*.xml"))
    if limit:
        ead_files = ead_files[:limit]
    if not ead_files:
        print(f"No .xml files found in {ead_dir}", file=sys.stderr)
        return

    total_docs = 0
    total_errors = 0
    n_files = len(ead_files)
    # Progress report every REPORT_EVERY files
    REPORT_EVERY = 100

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

        _bulk(client, index_name, docs)
        total_docs += len(docs)
        print(f"{len(docs)} docs indexed.", flush=True)

        if file_idx % REPORT_EVERY == 0:
            elapsed_so_far = time.time() - _start
            print(f"  → File {file_idx}… ({elapsed_so_far:.0f}s elapsed, {total_docs} docs so far)", flush=True)

    client.indices.put_settings(index=index_name, settings={"refresh_interval": "1s"})
    client.indices.refresh(index=index_name)

    elapsed = time.time() - _start
    print(f"\nDone. {total_docs} documents indexed from {n_files - total_errors} files "
          f"({total_errors} errors) in {elapsed:.1f}s ({elapsed/60:.1f}min).")

    # Final search perf check
    print(f"Total documents in index: {client.count(index=index_name)['count']}")
    for query in ["archives", "manuscrit", "Richelieu"]:
        t0 = time.time()
        res = client.search(index=index_name, size=10, track_total_hits=True,
                            query={"multi_match": {"query": query, "fields": ["title", "scope_content"]}})
        ms = (time.time() - t0) * 1000
        print(f"  Search '{query}': {res['hits']['total']['value']} hits, {ms:.0f}ms")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Index EAD files into Elasticsearch.")
    parser.add_argument(
        "ead_dir",
        nargs="?",
        default=str(Path(__file__).parent.parent.parent / "data"),
        help="Directory containing EAD XML files (default: ../../data)",
    )
    parser.add_argument("--host", default="http://localhost:9200", help="Elasticsearch URL")
    parser.add_argument("--user", default="elastic", help="Elasticsearch user (with --password)")
    parser.add_argument("--password", default="", help="Elasticsearch password (empty = no auth)")
    parser.add_argument("--index", default="ead_components", help="Elasticsearch index name")
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
        user=args.user,
        password=args.password,
        index_name=args.index,
        shallow=args.shallow,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
