"""
EAD indexer — parse a directory of EAD files and push documents to Elasticsearch.

Usage:
    python indexer.py [EAD_DIR] [--host HOST] [--user USER] [--password PWD] [--index INDEX]
                      [--liaisons FILE]

Files linked in liaisons.tsv (Calames inclusion / succession, see liaisons.py)
are indexed as one hierarchy: an attached file's root becomes a child of its
parent file's root, and inherits from it.

Defaults:
    EAD_DIR   : ../../data
    HOST      : http://localhost:9200
    USER      : elastic (only used when a password is given)
    PASSWORD  : (empty — security disabled, local dev)
    INDEX     : ead_components
    LIAISONS  : EAD_DIR/liaisons.tsv (if present)
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

from ead_parser import Anchor, parse_ead, components_to_docs
from liaisons import LIAISONS_FILE, FileGraph, file_id_of, load_liaisons

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
        "tokenizer": {
            # Runs of letters or of digits: "Ms 1234", "MS.1234" and "ms1234" → ms, 1234
            "cote_tokens": {"type": "pattern", "pattern": "\\p{L}+|\\p{N}+", "group": 0},
        },
        "analyzer": {
            # Stop words are removed before folding: the French list contains accented forms.
            "fr_text": {
                "tokenizer": "standard",
                "filter": ["fr_elision", "lowercase", "fr_stop", "asciifolding", "fr_stemmer"],
            },
            # Without stemming nor stop words: bonus for exact matches and phrases.
            "fr_exact": {
                "tokenizer": "standard",
                "filter": ["fr_elision", "lowercase", "asciifolding"],
            },
            "cote": {"tokenizer": "cote_tokens", "filter": ["lowercase", "asciifolding"]},
        },
    },
}

_TEXT    = {"type": "text", "analyzer": "fr_text"}
_TEXT_KW = {**_TEXT, "fields": {"kw": {"type": "keyword", "ignore_above": 1024}}}
_KW      = {"type": "keyword", "ignore_above": 1024}
_INT     = {"type": "integer"}
_EXACT   = {"exact": {"type": "text", "analyzer": "fr_exact"}}
_TEXT_EXACT = {**_TEXT, "fields": _EXACT}

# Only the fields searched, filtered, aggregated or sorted on are mapped;
# everything else is kept in _source for display ("dynamic": false).
INDEX_MAPPINGS = {
    "dynamic": False,
    "properties": {
        # Full-text fields (fields with a .kw sub-field are also filtered exactly)
        "title":            {**_TEXT, "fields": {**_TEXT_KW["fields"], **_EXACT}},
        "abstract":         _TEXT_EXACT,
        "scope_content":    _TEXT_EXACT,
        "biography":        _TEXT_EXACT,
        "other_text":       _TEXT_EXACT,   # other descriptive text (custodhist, acqinfo, notes…)
        "date_display":     _TEXT,
        "ancestor_titles":  _TEXT,
        "unitid":           {**_TEXT, "fields": {**_TEXT_KW["fields"],
                                                 "cote": {"type": "text", "analyzer": "cote"}}},
        "creator_names":    _TEXT_KW,
        # Authorities: <field> = own + inherited (filters, display), <field>_own = own only
        "subjects":         _TEXT,
        "geo_names":        _TEXT,
        "genre_forms":      _TEXT,
        "corp_names":       _TEXT,
        "pers_names":       _TEXT_KW,
        "fam_names":        _TEXT,
        "subjects_own":     _TEXT_EXACT,
        "geo_names_own":    _TEXT_EXACT,
        "genre_forms_own":  _TEXT_EXACT,
        "corp_names_own":   _TEXT_EXACT,
        "pers_names_own":   _TEXT_EXACT,
        "fam_names_own":    _TEXT_EXACT,
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
        "ead_ids":          _KW,   # the component's file and the files containing it
        "file_root":        {"type": "boolean"},
        "children_count":   _INT,
        "parent_children_count": _INT,
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


def build_graph(ead_files: list[Path], liaisons_path: Path | None) -> FileGraph:
    """Place the files according to the liaisons (no liaisons file: all top-level)."""
    liaisons = load_liaisons(liaisons_path)
    return FileGraph(liaisons, {p.name: file_id_of(p) if liaisons else None for p in ead_files})


def file_docs(ead_file: Path, graph: FileGraph, anchor: Anchor | None) -> list[dict]:
    """Parse a file into documents, attached under `anchor` (its parent file's root)."""
    name = ead_file.name
    siblings = graph.children_of(graph.parent_of(name) if anchor else None)
    rank = siblings.index(name) if name in siblings else len(siblings)
    position = (anchor.own_children_count if anchor else 0) + rank
    docs = components_to_docs(parse_ead(ead_file), anchor, position,
                              attached_count=len(graph.children_of(name)))
    for doc in docs:
        doc["source_file"] = name
    return docs


def _root_doc(client: Elasticsearch, index_name: str, file_name: str) -> dict | None:
    res = client.search(index=index_name, size=1, query={"bool": {"filter": [
        {"term": {"source_file": file_name}}, {"term": {"file_root": True}}]}})
    hits = res["hits"]["hits"]
    return hits[0]["_source"] if hits else None


def index_file(client: Elasticsearch, index_name: str, ead_file: Path,
               graph: FileGraph | None = None) -> dict[str, int]:
    """
    (Re)index an EAD file: drop the documents previously produced by this file,
    then push the new ones, attached under its parent file when the graph gives
    one (the parent must already be indexed, otherwise the file stands alone
    until the parent is). The files attached below it are reindexed too: they
    inherit from it.

    Returns {file name: documents indexed}. Raises on parse error of ead_file
    (its previous documents are kept in that case); an attached file that fails
    is skipped with its own subtree.
    """
    graph = graph or FileGraph({}, {ead_file.name: None})
    parent = graph.parent_of(ead_file.name)
    parent_doc = _root_doc(client, index_name, parent) if parent else None
    counts: dict[str, int] = {}
    _index_subtree(client, index_name, ead_file, graph,
                   Anchor.from_doc(parent_doc) if parent_doc else None, counts, raise_errors=True)
    return counts


def _index_subtree(client: Elasticsearch, index_name: str, ead_file: Path, graph: FileGraph,
                   anchor: Anchor | None, counts: dict[str, int], raise_errors: bool = False) -> None:
    try:
        docs = file_docs(ead_file, graph, anchor)
    except Exception as exc:
        if raise_errors:
            raise
        print(f"{ead_file.name} : ERREUR {exc} (fichiers rattachés ignorés)", file=sys.stderr)
        return
    remove_file(client, index_name, ead_file.name)
    _bulk(client, index_name, docs, refresh="wait_for")
    counts[ead_file.name] = len(docs)
    child_anchor = Anchor.from_doc(docs[0])
    for child in graph.children_of(ead_file.name):
        _index_subtree(client, index_name, ead_file.parent / child, graph, child_anchor, counts)


def sync_attached(client: Elasticsearch, index_name: str, graph: FileGraph, file_name: str) -> None:
    """
    Refresh, after files were attached under / detached from `file_name`, the
    children count of its root, and the positions and siblings count of the
    root's children (without reindexing them).
    """
    root = _root_doc(client, index_name, file_name)
    if root is None:
        return
    res = client.search(index=index_name, size=10000, source_includes=["source_file"],
                        query={"bool": {"filter": [{"term": {"parent_id": root["node_id"]}},
                                                   {"term": {"file_root": True}}]}})
    attached = {h["_source"]["source_file"]: h["_id"] for h in res["hits"]["hits"]}
    own = root.get("own_children_count", root.get("children_count") or 0)
    total = own + len(attached)
    order = graph.children_of(file_name)
    actions = [{"_op_type": "update", "_index": index_name, "_id": root["node_id"],
                "doc": {"children_count": total}}]
    for name, doc_id in attached.items():
        rank = order.index(name) if name in order else len(order)
        actions.append({"_op_type": "update", "_index": index_name, "_id": doc_id,
                        "doc": {"position": own + rank}})
    helpers.bulk(client, actions, refresh="wait_for")
    client.update_by_query(
        index=index_name, conflicts="proceed", refresh=True,
        query={"term": {"parent_id": root["node_id"]}},
        script={"source": "ctx._source.parent_children_count = params.n", "params": {"n": total}},
    )


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
    liaisons_path: Path | None = None,
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

    liaisons_path = liaisons_path or ead_dir / LIAISONS_FILE
    graph = build_graph(ead_files, liaisons_path)
    paths = {p.name: p for p in ead_files}
    attached = sum(1 for p in ead_files if graph.parent_of(p.name))
    print(f"Liaisons : {liaisons_path if liaisons_path.is_file() else 'aucune'} "
          f"({attached} fichiers rattachés à un autre)")
    # Parents first: an attached file is built from its parent root's document.
    ead_files = [paths[name] for name in graph.order()]
    anchors: dict[str, Anchor] = {}

    total_docs = 0
    total_errors = 0
    n_files = len(ead_files)
    # Progress report every REPORT_EVERY files
    REPORT_EVERY = 100

    for file_idx, ead_file in enumerate(ead_files, 1):
        print(f"[{file_idx}/{n_files}] {ead_file.name}...", end=" ", flush=True)
        try:
            # A file whose parent failed is indexed standalone.
            docs = file_docs(ead_file, graph, anchors.get(graph.parent_of(ead_file.name)))
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            total_errors += 1
            continue

        if graph.children_of(ead_file.name):
            anchors[ead_file.name] = Anchor.from_doc(docs[0])
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
    parser.add_argument("--liaisons", default=None,
                        help="Calames liaisons.tsv (default: EAD_DIR/liaisons.tsv if present)")

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
        liaisons_path=Path(args.liaisons) if args.liaisons else None,
    )


if __name__ == "__main__":
    main()
