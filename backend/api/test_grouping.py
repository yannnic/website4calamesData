"""
Teste : le regroupement des résultats de /search (règle de couverture par défaut,
règle des N frères avec sibling_grouping) : quels parents remplacent leurs
descendants trouvés, et les totaux renvoyés.

Indexe data/test/test_grouping*.xml dans un index temporaire, interroge /search et
compare aux résultats attendus décrits en tête de chaque fichier XML.
Ignorés si Elasticsearch ne répond pas sur ES_HOST (défaut : http://localhost:9200).

    cd backend
    python -m pytest api/test_grouping.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND  = Path(__file__).parent.parent
TEST_DIR = BACKEND.parent / "data" / "test"
sys.path.insert(0, str(BACKEND / "indexer"))

from indexer import create_index, index_file, make_client  # noqa: E402

import api.main as main  # noqa: E402

ES_HOST    = os.getenv("ES_HOST", "http://localhost:9200")
TEST_INDEX = "ead_test_grouping_pytest"


@pytest.fixture(scope="module")
def client():
    es = make_client(ES_HOST, os.getenv("ES_USER", ""), os.getenv("ES_PASSWORD", ""))
    try:
        es.info()
    except Exception:
        pytest.skip(f"Elasticsearch indisponible sur {ES_HOST}")

    es.indices.delete(index=TEST_INDEX, ignore_unavailable=True)
    create_index(es, TEST_INDEX)
    for name in ("test_grouping.xml", "test_grouping_siblings.xml"):
        index_file(es, TEST_INDEX, TEST_DIR / name)

    previous, main.ES_INDEX = main.ES_INDEX, TEST_INDEX
    try:
        with TestClient(main.app) as c:
            yield c
    finally:
        main.ES_INDEX = previous
        es.indices.delete(index=TEST_INDEX, ignore_unavailable=True)


def search(client, ead_id: str, **params) -> dict:
    res = client.get("/search", params={"q": "zephyrin", "ead_id": ead_id, "limit": 100, **params})
    assert res.status_code == 200, res.text
    return res.json()


def entries(res: dict) -> dict[str, int | None]:
    """{component id (after '#'): grouped_count, or None when not grouped}."""
    return {h["node_id"].split("#", 1)[1]: h.get("grouped_count") for h in res["hits"]}


# ---------------------------------------------------------------------------
# test_grouping.xml — règle de couverture
# ---------------------------------------------------------------------------

def test_coverage(client):
    res = search(client, "test-grouping")
    assert entries(res) == {
        "serie-cov":    3,     # 3 pièces sur 4 : 75 %
        "under-1":      None,  # 2 sur 4 : sous le seuil, les pièces restent
        "under-2":      None,
        "serie-nested": 4,     # deux sous-séries regroupées, puis la série
        "serie-self":   None,  # correspond elle-même...
        "self-1":       None,  # ...et sa pièce aussi : les deux apparaissent
    }
    assert res["total"] == 6
    assert res["total_hits"] == 11


def test_coverage_is_recursive(client):
    """Les sous-séries regroupées sont absorbées par la série, pas listées."""
    ids = entries(search(client, "test-grouping"))
    assert not {"nested-1", "nested-2", "nested-1-1", "nested-2-2"} & ids.keys()


def test_fonds_below_threshold(client):
    """3 séries sur 5 trouvées ou regroupées : 60 %, le fonds n'est pas regroupé."""
    assert all(h["depth"] > 0 for h in search(client, "test-grouping")["hits"])


def test_siblings_rule(client):
    res = search(client, "test-grouping", sibling_grouping="true")
    assert entries(res) == {
        "serie-cov":  3,
        "under-1":    None, "under-2":    None,
        "nested-1-1": None, "nested-1-2": None,
        "nested-2-1": None, "nested-2-2": None,
        "serie-self": None, "self-1":     None,
    }
    assert res["total_hits"] == 11


# ---------------------------------------------------------------------------
# test_grouping_siblings.xml — couverture vs règle des N frères
# ---------------------------------------------------------------------------

def test_siblings_file_coverage(client):
    """3 pièces sur 10 : la couverture ne regroupe pas."""
    res = search(client, "test-grouping-siblings")
    assert entries(res) == {"a-1": None, "a-2": None, "a-3": None, "b-1": None, "b-2": None}


def test_siblings_file_siblings_rule(client):
    """3 frères trouvés : la série A est regroupée ; 2 seulement en série B."""
    res = search(client, "test-grouping-siblings", sibling_grouping="true")
    assert entries(res) == {"serie-a": 3, "b-1": None, "b-2": None}
    assert res["total"] == 3
    assert res["total_hits"] == 5


# ---------------------------------------------------------------------------
# Classement, pagination, cas sans regroupement
# ---------------------------------------------------------------------------

def test_grouped_entry_scores_as_best_descendant(client):
    hits = search(client, "test-grouping")["hits"]
    assert all(h.get("_rankingScore") for h in hits)
    assert max(h["_rankingScore"] for h in hits) == pytest.approx(1.0)


def test_pagination_matches_full_list(client):
    full = [h["node_id"] for h in search(client, "test-grouping")["hits"]]
    paged = []
    for offset in range(0, len(full), 4):
        res = search(client, "test-grouping", limit=4, offset=offset)
        assert res["total"] == len(full)
        paged += [h["node_id"] for h in res["hits"]]
    assert paged == full


def test_level_filter_disables_grouping(client):
    res = search(client, "test-grouping", level="item")
    assert res["total"] == res["total_hits"] == 10
    assert all(v is None for v in entries(res).values())
