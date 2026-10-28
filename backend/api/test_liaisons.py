"""
Teste : l'indexation et l'API de fichiers EAD liés (liaisons.tsv) : ordre des
fichiers rattachés sous leur parent, héritage à travers les fichiers, fil d'Ariane,
filtre ead_id, recherche plein texte (texte non structuré, titres des ancêtres,
autorités propres / héritées, cotes, expressions), dépliage de l'arbre (nombre de descendants, /children?details,
/subtree), mise à jour incrémentale (comme le watcher) et /raw.

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
                     "Correspondance, volume 1", "Correspondance, volume 1 bis", "Manuscrits isolés"]
# Le volume 2 continué par son successeur (vol2_suite) : un seul fonds.
VOL2_CHILDREN = ["Lettre sur les lichens", "Lettre sur les algues"]


@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("liaisons")
    for name in FILES + ["liaisons.tsv"]:
        shutil.copy(TEST_DIR / name, d / name)
    return d


def test_graph_order(corpus):
    graph = build_graph(sorted(corpus.glob("*.xml")), corpus / "liaisons.tsv")
    assert graph.order()[0] == MAITRE
    assert graph.children_of(MAITRE) == ["test_liaisons_vol2.xml", "test_liaisons_vol1.xml",
                                         "test_liaisons_vol1b.xml", "test_liaisons_orphelin.xml"]
    assert graph.successors_of("test_liaisons_vol2.xml") == ["test_liaisons_vol2_suite.xml"]
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


def test_succession_merged_into_head(client):
    vol2 = get(client, "/fonds/test-liaisons-vol2")
    children = get(client, "/children", node_id=vol2["node_id"])
    assert [c["title"] for c in children] == VOL2_CHILDREN
    assert vol2["children_count"] == 2 and vol2["merged_file_ids"] == ["9004"]
    # La racine du successeur n'est pas un composant ; son adresse Calames mène à la tête.
    assert client.get("/fonds/test-liaisons-vol2-suite").status_code == 404
    assert get(client, "/resolve", id="FileId-9004")["node_id"] == vol2["node_id"]
    algues = get(client, "/component", node_id="test-liaisons-vol2-suite#v2s-1")
    assert algues["parent_id"] == vol2["node_id"]
    assert algues["date_normal"] == "1896-1910".replace("-", "/")      # date de son propre fichier
    assert algues["ancestor_titles"] == ["Fonds Anselme Quillebeuf", "Correspondance, volume 2"]


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
    # Cotes des ancêtres, celle du maître comprise (fichier parent)
    assert item["ancestor_unitids"] == ["QB", "QB 1"]
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
    assert res["total_hits"] == 2      # avec la lettre de son successeur


def test_found_by_inherited_subject(client):
    # level=item : sans regroupement (la pièce couvre seule son fichier).
    res = get(client, "/search", q="botanique lichens", level="item", limit=100)
    assert [h["node_id"] for h in res["hits"]] == ["test-liaisons-vol2#v2-1"]


def ids(res):
    return [h["node_id"] for h in res["hits"]]


def test_fulltext_other_text(client):
    # <custodhist> : cherché (other_text), sans <head>
    res = get(client, "/search", q="lemarchand", limit=100)
    assert ids(res) == [master_root(client)["node_id"]]
    assert get(client, "/search", q="historique", limit=100)["total_hits"] == 0


def test_fulltext_ancestor_title_completes_query(client):
    # « quillebeuf » n'est que dans le titre du maître (et celui de v1-1)
    res = get(client, "/search", q="mousses quillebeuf", level="item", limit=100)
    assert ids(res) == ["test-liaisons-vol1#v1-2"]
    # Seul, le titre d'un ancêtre ne suffit pas : pas toutes les pièces du fonds.
    res = get(client, "/search", q="quillebeuf", level="item", limit=100)
    assert ids(res) == ["test-liaisons-vol1#v1-1"]


def test_fulltext_own_subject_first(client):
    # Les racines des fichiers rattachés héritent de « Botanique » ; le maître le déclare.
    res = get(client, "/search", q="botanique", level="fonds", limit=100)
    assert res["hits"][0]["node_id"] == master_root(client)["node_id"]
    assert res["total_hits"] > 1


def test_fulltext_cote_any_form(client):
    for q in ("QB 1/1", "qb1/1", "QB.1.1"):
        res = get(client, "/search", q=q, level="item", limit=100)
        assert ids(res)[0] == "test-liaisons-vol1#v1-1", q


def test_fulltext_phrase(client):
    assert ids(get(client, "/search", q='"sur les mousses"', level="item")) == ["test-liaisons-vol1#v1-2"]
    assert get(client, "/search", q='"les sur mousses"', level="item")["total_hits"] == 0


def test_tree_expansion(client):
    # 5 enfants, 11 descendants (fichiers rattachés et successeur compris)
    root = master_root(client)
    assert root["descendants_count"] == 11
    children = get(client, "/children", node_id=root["node_id"])
    assert {c["title"]: c["descendants_count"] for c in children}["Correspondance, volume 1"] == 2
    assert "scope_content" not in children[0]
    detailed = get(client, "/children", node_id=root["node_id"], details="true")
    assert "scope_content" in detailed[0]
    subtree = get(client, "/subtree", node_id=root["node_id"])
    assert subtree["total"] == 11 == len(subtree["nodes"])
    # Parents avant enfants : l'arbre se reconstruit dans l'ordre de la réponse.
    seen = {root["node_id"]}
    for n in subtree["nodes"]:
        assert n["parent_id"] in seen
        seen.add(n["node_id"])
    res = client.get("/subtree", params={"node_id": root["node_id"], "max": 5})
    assert res.status_code == 413

def test_incremental_detach_and_reindex(es, client, corpus):
    # Le watcher : suppression du successeur, puis mise à jour de sa tête.
    (corpus / "test_liaisons_vol2_suite.xml").unlink()
    remove_file(es, TEST_INDEX, "test_liaisons_vol2_suite.xml")
    graph = build_graph(sorted(corpus.glob("*.xml")), corpus / "liaisons.tsv")
    sync_attached(es, TEST_INDEX, graph, "test_liaisons_vol2.xml")
    vol2 = get(client, "/fonds/test-liaisons-vol2")
    assert [c["title"] for c in get(client, "/children", node_id=vol2["node_id"])] == VOL2_CHILDREN[:1]
    assert vol2["children_count"] == 1

    root = master_root(client)
    children = get(client, "/children", node_id=root["node_id"])
    expected = EXPECTED_CHILDREN
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
    # Par défaut sans les composants enfants ; children=true les inclut.
    assert 'id="v1-1"' not in res.text and "2 composant(s)" in res.text
    res = client.get("/raw", params={"node_id": root["node_id"], "children": "true"})
    assert 'id="v1-1"' in res.text and 'id="v1-2"' in res.text
