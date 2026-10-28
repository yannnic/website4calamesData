"""
Teste : les fonctions reprises de l'interface publique de Calames, sur
data/test/test_calames_affichage.xml : redirection des adresses Calames
(/resolve), rubriques de description, anciennes cotes, versions numériques,
titres d'œuvres, fonctions, provenance, organisme responsable, tri des
résultats et syntaxe de recherche (OR, -mot, ^début).
Ignorés si Elasticsearch ne répond pas sur ES_HOST.

    cd backend
    python -m pytest api/test_calames.py -v
"""

from __future__ import annotations

import json
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
TEST_INDEX = "ead_test_calames_pytest"
FILE       = "test_calames_affichage.xml"
ROOT       = "test-calames-affichage#auto-1"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    es = make_client(ES_HOST, os.getenv("ES_USER", ""), os.getenv("ES_PASSWORD", ""))
    try:
        es.info()
    except Exception:
        pytest.skip(f"Elasticsearch indisponible sur {ES_HOST}")
    es.indices.delete(index=TEST_INDEX, ignore_unavailable=True)
    create_index(es, TEST_INDEX)
    index_file(es, TEST_INDEX, TEST_DIR / FILE)

    data = tmp_path_factory.mktemp("calames")
    (data / "etablissements.json").write_text(json.dumps({"999999998": {
        "name": "Bibliothèque de démonstration", "address": ["1 rue du Test", "75000 Paris"],
        "phone": "01 00 00 00 00", "email": "demo@exemple.org", "website": "https://exemple.org"}}),
        encoding="utf-8")
    previous = main.ES_INDEX, main.DATA_DIR
    main.ES_INDEX, main.DATA_DIR = TEST_INDEX, data
    try:
        yield TestClient(main.app)   # sans lifespan : pas de réindexation du corpus de test
    finally:
        main.ES_INDEX, main.DATA_DIR = previous
        es.indices.delete(index=TEST_INDEX, ignore_unavailable=True)


@pytest.fixture(scope="module", autouse=True)
def es_client(client):
    # TestClient sans lifespan : le client Elasticsearch de l'API est créé ici.
    main._es = main.Elasticsearch(ES_HOST)


def get(client, path, **params):
    res = client.get(path, params=params)
    assert res.status_code == 200, res.text
    return res.json()


def ids(res):
    return [h["node_id"].split("#")[1] for h in res["hits"]]


def test_resolve_calames_urls(client):
    assert get(client, "/resolve", id="FileId-9100")["node_id"] == ROOT
    assert get(client, "/resolve", id="ca-1")["node_id"] == "test-calames-affichage#ca-1"
    assert client.get("/resolve", params={"id": "inconnu"}).status_code == 404


def test_description_sections_and_terms(client):
    root = get(client, "/component", node_id=ROOT)
    assert [s["tag"] for s in root["sections"]] == ["custodhist", "acqinfo", "relatedmaterial"]
    assert root["sections"][0]["text"] == "Conservé par la famille.\nDéposé en 1960."   # sans <head>
    assert root["unitid"] == "CA 1" and root["former_unitids"] == ["Anc 99"]
    assert root["dao"] == [{"href": "https://exemple.org/numerisation/ca-1", "title": "Fonds numérisé"}]
    assert root["work_titles_own"] == ["Le Cid"] and root["functions_own"] == ["Enseignement"]
    assert root["provenance"] == ["Dupuis, Jean"]
    assert root["repository_info"]["phone"] == "01 00 00 00 00"
    item = get(client, "/component", node_id="test-calames-affichage#ca-1")
    # Une ancienne cote seule n'est pas la cote du composant.
    assert item["unitid"] == "" and item["former_unitids"] == ["X 12"]
    assert item["dao"][0]["href"].endswith("/registre")      # daoloc, xlink:href
    assert item["work_titles"] == ["Le Cid"] and item["work_titles_own"] == []   # hérité


def test_former_cote_search(client):
    assert ids(get(client, "/search", q="anc 99"))[0] == "auto-1"
    assert ids(get(client, "/search", q="x12", level="item"))[0] == "ca-1"


def test_sort(client):
    res = get(client, "/search", ead_id="test-calames-affichage", level="item", sort="title_asc")
    assert ids(res) == ["ca-3", "ca-2", "ca-1"]       # Carnet, Lettre, Registre
    res = get(client, "/search", ead_id="test-calames-affichage", level="item", sort="date_asc")
    assert ids(res) == ["ca-1", "ca-2", "ca-3"]        # 1890 (héritée du fonds), 1900, 1950


def test_filters_and_facets(client):
    res = get(client, "/search", dao="true")
    assert sorted(ids(res)) == ["auto-1", "ca-1"]
    assert get(client, "/search")["facets"]["languages"]["fre"] == 4
    assert get(client, "/search", provenance="Dupuis, Jean", level="fonds")["total_hits"] == 1
    assert get(client, "/search", work_title="cid", level="fonds")["total_hits"] == 1
    assert get(client, "/search", function="enseignement", level="fonds")["total_hits"] == 1


def test_calames_query_syntax(client):
    assert sorted(ids(get(client, "/search", q="lettre OR carnet", level="item"))) == ["ca-2", "ca-3"]
    assert sorted(ids(get(client, "/search", q="lettre | carnet", level="item"))) == ["ca-2", "ca-3"]
    assert ids(get(client, "/search", q="^carn", level="item")) == ["ca-3"]
    assert get(client, "/search", q="lettre -lettre", level="item")["total_hits"] == 0
