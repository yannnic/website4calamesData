"""
Teste : find_element() (endpoint /raw) retrouve l'élément XML de chaque composant
indexé, avec ou sans @id (auto-N) ; l'XML d'un niveau sans ses composants enfants ;
et le repli de l'ead_id quand <eadid> est vide.

    cd backend/indexer
    python -m pytest test_find_element.py -v
"""

from pathlib import Path

import pytest
from lxml import etree

from ead_parser import components_to_docs, find_element, parse_ead, strip_child_components

TEST_DIR = Path(__file__).parent.parent.parent / "data" / "test"

MIXED_IDS = """<?xml version="1.0" encoding="UTF-8"?>
<ead xmlns="urn:isbn:1-931666-22-9">
  <eadheader><eadid>test-mixed-ids</eadid></eadheader>
  <archdesc level="fonds">
    <did><unittitle>Racine</unittitle></did>
    <dsc>
      <c level="series"><did><unittitle>Série sans id</unittitle></did>
        <c level="file"><did><unittitle>Dossier sans id</unittitle></did></c>
        <c id="avec-id" level="file"><did><unittitle>Dossier avec id</unittitle></did>
          <c level="item"><did><unittitle>Pièce sans id</unittitle></did></c>
        </c>
      </c>
      <c level="series"><did><unittitle>Seconde série sans id</unittitle></did></c>
    </dsc>
  </archdesc>
</ead>
"""


def _title(el: etree._Element) -> str:
    return "".join(el.find("{*}did/{*}unittitle").itertext()).strip()


def _check_all(path: Path) -> int:
    docs = components_to_docs(parse_ead(path))
    for doc in docs:
        el = find_element(path, doc["node_id"])
        assert el is not None, doc["node_id"]
        assert _title(el) == doc["title"], doc["node_id"]
    return len(docs)


def test_mixed_ids(tmp_path):
    path = tmp_path / "mixed.xml"
    path.write_text(MIXED_IDS, encoding="utf-8")
    assert _check_all(path) == 6
    assert _title(find_element(path, "test-mixed-ids#auto-4")) == "Pièce sans id"
    assert find_element(path, "test-mixed-ids#auto-99") is None


@pytest.mark.parametrize("path", sorted(TEST_DIR.glob("*.xml")), ids=lambda p: p.name)
def test_corpus_files(path):
    _check_all(path)


def test_empty_eadid_falls_back_to_identifier(tmp_path):
    path = tmp_path / "empty.xml"
    path.write_text(MIXED_IDS.replace("<eadid>test-mixed-ids</eadid>",
                                      '<eadid identifier="FR-1_CALAMESFileId-7"/>'), encoding="utf-8")
    assert parse_ead(path).node_id == "FR-1_CALAMESFileId-7#auto-1"
    path.write_text(MIXED_IDS.replace("<eadid>test-mixed-ids</eadid>", "<eadid/>"), encoding="utf-8")
    assert parse_ead(path).node_id == "empty#auto-1"


def test_strip_child_components(tmp_path):
    path = tmp_path / "mixed.xml"
    path.write_text(MIXED_IDS, encoding="utf-8")
    serie = find_element(path, "test-mixed-ids#auto-2")
    assert strip_child_components(serie) == 2        # ses deux dossiers, pas la pièce
    xml = etree.tostring(serie, encoding="unicode")
    assert "Série sans id" in xml and "Dossier" not in xml
    assert "2 composant(s) <c> non affiché(s)" in xml
    root = find_element(path, "test-mixed-ids#auto-1")
    assert strip_child_components(root) == 2         # les deux séries, sous <dsc>


def test_shared_eadid_made_unique_by_oai_number(tmp_path):
    # Deux notices au même eadid, nommées par le moissonneur avec leur numéro OAI.
    for n in ("4412", "4439"):
        (tmp_path / f"FR-341729802_Fonds_oai{n}.xml").write_text(
            MIXED_IDS.replace("<eadid>test-mixed-ids</eadid>", "<eadid>FR-341729802 Fonds</eadid>"),
            encoding="utf-8")
    ids = {parse_ead(p).ead_id for p in tmp_path.glob("*.xml")}
    assert ids == {"FR-341729802 Fonds_oai4412", "FR-341729802 Fonds_oai4439"}
    path = tmp_path / "FR-341729802_Fonds_oai4412.xml"
    assert find_element(path, "FR-341729802 Fonds_oai4412#auto-1") is not None
