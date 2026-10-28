"""
Tests du paramètre corpus=test : le corpus de test (data/test) est indexé au
démarrage de l'API et interrogeable sans la relancer.
Ignorés si Elasticsearch ne répond pas sur ES_HOST.

    cd backend
    python -m pytest api/test_corpus.py -v
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

import api.main as main

ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")


@pytest.fixture(scope="module")
def client():
    try:
        main.Elasticsearch(ES_HOST).info()
    except Exception:
        pytest.skip(f"Elasticsearch indisponible sur {ES_HOST}")
    previous, main.TEST_ES_INDEX = main.TEST_ES_INDEX, "ead_test_corpus_pytest"
    try:
        with TestClient(main.app) as c:   # le démarrage indexe le corpus de test
            yield c
    finally:
        main._es.indices.delete(index=main.TEST_ES_INDEX, ignore_unavailable=True)
        main.TEST_ES_INDEX = previous


def test_test_corpus_is_indexed_and_selected(client):
    res = client.get("/fonds", params={"corpus": "test"})
    assert res.status_code == 200
    assert "test-liaisons-maitre" in {f["ead_id"] for f in res.json()}
    res = client.get("/search", params={"q": "zephyrin", "corpus": "test"})
    assert res.json()["total_hits"] > 0


def test_raw_and_files_use_the_test_directory(client):
    res = client.get("/raw", params={"node_id": "test-liaisons-vol1#v1-1", "corpus": "test"})
    assert res.status_code == 200 and "fougères" in res.text
    files = client.get("/files", params={"corpus": "test"}).json()
    assert not files["upload_enabled"]
    assert "test_liaisons_maitre.xml" in {f["name"] for f in files["files"]}


def test_unknown_corpus(client):
    assert client.get("/fonds", params={"corpus": "nimporte"}).status_code == 400
