"""
Teste : l'extraction de l'EAD d'une réponse OAI-PMH sans les namespaces hérités
du wrapper (balises et attributs), y compris quand l'EAD contient des
commentaires ou des instructions de traitement ; des noms de fichiers uniques
même quand plusieurs notices ont le même eadid ; une notice refusée par le
serveur est rejetée sans arrêter le moissonnage. Sans réseau.

    cd backend/harvester
    python -m pytest test_harvester.py -v
"""

import pytest
import requests
from lxml import etree

from harvester import OAI_NS, RecordRejected, _copy_without_ns, _filename_from_ead, get_ead

RECORD = f"""<OAI-PMH xmlns="{OAI_NS}"><GetRecord><record><metadata>
<ead xmlns="urn:isbn:1-931666-22-9" xmlns:xlink="http://www.w3.org/1999/xlink">
  <!-- commentaire dans l'EAD -->
  <?traitement exemple?>
  <eadheader><eadid>test</eadid></eadheader>
  <archdesc level="fonds"><did><unittitle>Fonds</unittitle></did>
    <dao xlink:href="http://exemple.org/image.jpg"/>
  </archdesc>
</ead>
</metadata></record></GetRecord></OAI-PMH>"""


def test_copy_without_ns_keeps_comments_and_strips_namespaces():
    metadata = etree.fromstring(RECORD.encode("utf-8")).find(f".//{{{OAI_NS}}}metadata")
    ead = _copy_without_ns(metadata[0])
    xml = etree.tostring(ead, encoding="unicode")
    assert xml.startswith("<ead>") and "xmlns" not in xml
    assert "<!-- commentaire dans l'EAD -->" in xml and "<?traitement exemple?>" in xml
    assert ead.find("archdesc/did/unittitle").text == "Fonds"
    assert ead.find("archdesc/dao").get("href") == "http://exemple.org/image.jpg"


def _ead(eadid: str) -> bytes:
    return f"<ead><eadheader><eadid>{eadid}</eadid></eadheader></ead>".encode("utf-8")


def test_filename_unique_per_record():
    # Même eadid pour deux notices (cas réel FR-341729802) : deux fichiers distincts.
    a = _filename_from_ead(_ead("FR-341729802 Fonds"), "oai:oaicalames.abes.fr:4412")
    b = _filename_from_ead(_ead("FR-341729802 Fonds"), "oai:oaicalames.abes.fr:4439")
    assert (a, b) == ("FR-341729802_Fonds_oai4412.xml", "FR-341729802_Fonds_oai4439.xml")
    # L'eadid contient déjà le FileId de la notice : pas de suffixe.
    assert _filename_from_ead(_ead("FR-751039801_CALAMESFileId-1077"), "oai:oaicalames.abes.fr:1077") \
        == "FR-751039801_CALAMESFileId-1077.xml"
    # Il contient un autre FileId (10773, ou celui d'une autre notice) : suffixe.
    assert _filename_from_ead(_ead("X_CALAMESFileId-10773"), "oai:oaicalames.abes.fr:1077") \
        == "X_CALAMESFileId-10773_oai1077.xml"
    # Plus de « .xml.xml » quand l'eadid se termine par .xml
    assert _filename_from_ead(_ead("FRCGMBPF-751069803-03b.xml"), "oai:oaicalames.abes.fr:53") \
        == "FRCGMBPF-751069803-03b_oai53.xml"
    # eadid vide : identifiant OAI
    assert _filename_from_ead(_ead(""), "oai:oaicalames.abes.fr:5893") == "oai_oaicalames.abes.fr_5893.xml"


class FakeResponse:
    def __init__(self, status, content=b""):
        self.status_code, self.content, self.headers = status, content, {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)


class FakeSession:
    def __init__(self, response):
        self.response = response

    def get(self, url, timeout):
        return self.response


OAI_ERROR = f'''<OAI-PMH xmlns="{OAI_NS}"><error code="idDoesNotExist">not found</error></OAI-PMH>'''.encode()


@pytest.mark.parametrize("response", [FakeResponse(404), FakeResponse(200, OAI_ERROR),
                                      FakeResponse(200, b"<html><p>erreur</html")],
                         ids=["http-404", "erreur-oai", "non-xml"])
def test_record_rejected(response):
    with pytest.raises(RecordRejected):
        get_ead("http://oai", "oai_ead", "oai:x:1", 0, FakeSession(response))


def test_record_ok():
    content = RECORD.encode("utf-8")
    assert get_ead("http://oai", "oai_ead", "oai:x:1", 0, FakeSession(FakeResponse(200, content))).startswith(b"<?xml")
