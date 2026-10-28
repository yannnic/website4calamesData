"""
Teste : find_element() (endpoint /raw) retrouve l'élément XML de chaque composant
indexé, avec ou sans @id (auto-N) ; et le repli de l'ead_id quand <eadid> est vide.

    cd backend/indexer
    python -m pytest test_find_element.py -v
"""

from pathlib import Path

import pytest
from lxml import etree

from ead_parser import components_to_docs, find_element, parse_ead

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
