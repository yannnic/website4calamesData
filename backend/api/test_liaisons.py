"""
Tests des liaisons entre fichiers EAD (liaisons.tsv) sur un index Elasticsearch réel.

Indexe data/test/test_liaisons*.xml avec data/test/liaisons.tsv dans un index
temporaire et vérifie l'arborescence décrite en tête de test_liaisons_maitre.xml.
Les tests sur Elasticsearch sont ignorés s'il ne répond pas sur ES_HOST.

    cd backend
    python -m pytest api/test_liaisons.py -v
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND  = Path(__file__).parent.parent
TEST_DIR = BACKEND.parent / "data" / "test"
sys.path.insert(0, str(BACKEND / "indexer"))

from indexer import build_graph, index_directory, index_file, make_client, remove_file, sync_attached  # noqa: E402

import api.main as main  # noqa: E402

ES_HOST    = os.getenv("ES_HOST", "http://localhost:9200")
TEST_INDEX = "ead_test_liaisons_pytest"

MAITRE  = "test_liaisons_maitre.xml"
FILES   = [MAITRE, "test_liaisons_vol1.xml", "test_liaisons_vol2.xml",
           "test_liaisons_vol2_suite.xml", "test_liaisons_vol1b.xml", "test_liaisons_orphelin.xml"]
EXPECTED_CHILDREN = ["Présentation du fonds", "Correspondance, volume 2",
                     "Correspondance, volume 2, suite", "Correspondance, volume 1",
                     "Correspondance, volume 1 bis", "Manuscrits isolés"]


@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("liaisons")
    for name in FILES + ["liaisons.tsv"]:
        shutil.copy(TEST_DIR / name, d / name)
    return d


def test_graph_order(corpus):
    graph = build_graph(sorted(corpus.glob("*.xml")), corpus / "liaisons.tsv")
    assert graph.order()[0] == MAITRE
    assert graph.children_of(MAITRE) == ["test_liaisons_vol2.xml", "test_liaisons_vol2_suite.xml",
                                         "test_liaisons_vol1.xml", "test_liaisons_vol1b.xml",
                                         "test_liaisons_orphelin.xml"]
    # Parent absent du corpus (9999) : rattaché au plus proche ancêtre présent.
    assert graph.parent_of("test_liaisons_orphelin.xml") == MAITRE


def test_no_liaisons_file(corpus):
    graph = build_graph(sorted(corpus.glob("*.xml")), corpus / "absent.tsv")
    assert all(graph.parent_of(n) is None for n in FILES)


@pytest.fixture(scope="module")
def es(corpus):
    es = make_client(ES_HOST, os.getenv("ES_USER", ""), os.getenv("ES_PASSWORD", ""))
    try:
        es.info()
    except Exception:
        pytest.skip(f"Elasticsearch indisponible sur {ES_HOST}")
    index_directory(corpus, ES_HOST, os.getenv("ES_USER", ""), os.getenv("ES_PASSWORD", ""), TEST_INDEX)
    yield es
    es.indices.delete(index=TEST_INDEX, ignore_unavailable=True)


@pytest.fixture(scope="module")
def client(es):
    previous, main.ES_INDEX = main.ES_INDEX, TEST_INDEX
    try:
        with TestClient(main.app) as c:
            yield c
    finally:
        main.ES_INDEX = previous


def get(client, path: str, **params):
    res = client.get(path, params=params)
    assert res.status_code == 200, res.text
    return res.json()


def master_root(client) -> dict:
    return get(client, "/fonds/test-liaisons-maitre")


def test_fonds_lists_top_level_only(client):
    assert [f["ead_id"] for f in get(client, "/fonds")] == ["test-liaisons-maitre"]


def test_children_order(client):
    root = master_root(client)
    children = get(client, "/children", node_id=root["node_id"])
    assert [c["title"] for c in children] == EXPECTED_CHILDREN
    assert root["children_count"] == len(EXPECTED_CHILDREN)


def test_attached_file_root(client):
    vol1 = get(client, "/fonds/test-liaisons-vol1")
    assert vol1["depth"] == 1
    assert vol1["parent_id"] == master_root(client)["node_id"]
    assert vol1["parent_children_count"] == len(EXPECTED_CHILDREN)
    assert vol1["children_count"] == 2


def test_inheritance_across_files(client):
    item = get(client, "/component", node_id="test-liaisons-vol1#v1-1")
    assert item["depth"] == 2
    assert item["ancestor_titles"] == ["Fonds Anselme Quillebeuf", "Correspondance, volume 1"]
    assert item["ead_ids"] == ["test-liaisons-maitre", "test-liaisons-vol1"]
    assert item["subjects_norm"] == ["Correspondance", "Botanique"]
    assert item["access_restrict"] == "Communicable sur rendez-vous"
    assert item["languages"] == ["fre"]
    assert item["repository_id"] == "999999999"
    # Date : celle du fichier rattaché, pas celle du maître.
    assert item["date_normal"] == "1850/1880"


def test_breadcrumb(client):
    ancestors = get(client, "/ancestors", node_id="test-liaisons-vol1#v1-1")
    assert [a["title"] for a in ancestors] == ["Fonds Anselme Quillebeuf", "Correspondance, volume 1"]


def test_search_restricted_to_master_covers_attached_files(client):
    res = get(client, "/search", q="lettre", ead_id="test-liaisons-maitre", limit=100)
    assert res["total_hits"] == 4
    res = get(client, "/search", q="lettre", ead_id="test-liaisons-vol2", limit=100)
    assert res["total_hits"] == 1


def test_found_by_inherited_subject(client):
    # level=item : sans regroupement (la pièce couvre seule son fichier).
    res = get(client, "/search", q="botanique lichens", level="item", limit=100)
    assert [h["node_id"] for h in res["hits"]] == ["test-liaisons-vol2#v2-1"]


def test_incremental_detach_and_reindex(es, client, corpus):
    # Le watcher : suppression d'un fichier rattaché, puis mise à jour du maître.
    (corpus / "test_liaisons_vol2_suite.xml").unlink()
    remove_file(es, TEST_INDEX, "test_liaisons_vol2_suite.xml")
    graph = build_graph(sorted(corpus.glob("*.xml")), corpus / "liaisons.tsv")
    sync_attached(es, TEST_INDEX, graph, MAITRE)

    root = master_root(client)
    children = get(client, "/children", node_id=root["node_id"])
    expected = [t for t in EXPECTED_CHILDREN if t != "Correspondance, volume 2, suite"]
    assert [c["title"] for c in children] == expected
    assert root["children_count"] == len(expected)
    orphelin = get(client, "/fonds/test-liaisons-orphelin")
    assert orphelin["position"] == len(expected) - 1
    assert orphelin["parent_children_count"] == len(expected)

    # Réindexer le maître réindexe aussi les fichiers qui en héritent.
    counts = index_file(es, TEST_INDEX, corpus / MAITRE, graph)
    assert sorted(counts) == sorted(n for n in FILES if n != "test_liaisons_vol2_suite.xml")
    children = get(client, "/children", node_id=master_root(client)["node_id"])
    assert [c["title"] for c in children] == expected


def test_raw(client, corpus, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", corpus)
    res = client.get("/raw", params={"node_id": "test-liaisons-vol1#v1-1"})
    assert res.status_code == 200, res.text
    assert "fougères" in res.text and "<c" in res.text
    # Racine sans @id (auto-1) : l'archdesc.
    root = get(client, "/fonds/test-liaisons-vol1")
    res = client.get("/raw", params={"node_id": root["node_id"]})
    assert res.status_code == 200 and "<archdesc" in res.text
