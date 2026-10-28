"""
Teste : le placement et l'ordre des fichiers EAD selon liaisons.tsv (inclusion,
succession, parent absent, FileId partagé, boucle), la lecture de liaisons.tsv et
celle du FileId dans l'eadid. Sans Elasticsearch.

    cd backend/indexer
    python -m pytest test_file_graph.py -v

Colonnes de liaisons.tsv : FileId, libellé, chemin, indicateur, précédent, parent, rang.
"""

from pathlib import Path

from liaisons import FileGraph, file_id_of, parse_liaisons


def tsv(*rows: tuple) -> str:
    """rows: (FileId, libellé, précédent, parent, rang)."""
    return "\n".join(f"{fid}\t{label}\tadmin;1;\t0\t{prev}\t{parent}\t{rank}"
                     for fid, label, prev, parent, rank in rows)


def graph(text: str, files: dict[str, str]) -> FileGraph:
    """files: {nom de fichier: FileId}, FileId lu dans @identifier (pas seulement @url)."""
    return FileGraph(parse_liaisons(text), {name: (fid, False) for name, fid in files.items()})


# ---------------------------------------------------------------------------
# Inclusion
# ---------------------------------------------------------------------------

def test_inclusion_order_by_rank_then_label():
    g = graph(tsv(("1", "Maître", 0, 0, 0),
                  ("2", "Volume B", 0, 1, 2),
                  ("3", "Volume C", 0, 1, 1),
                  ("4", "Volume A", 0, 1, 2)),
              {"maitre.xml": "1", "b.xml": "2", "c.xml": "3", "a.xml": "4"})
    # Rang 1 d'abord, puis à rang égal l'ordre du libellé.
    assert g.children_of("maitre.xml") == ["c.xml", "a.xml", "b.xml"]
    assert all(g.parent_of(n) == "maitre.xml" for n in ("a.xml", "b.xml", "c.xml"))
    assert g.children_of(None) == ["maitre.xml"]


def test_nested_inclusion():
    g = graph(tsv(("1", "Maître", 0, 0, 0),
                  ("2", "Sous-maître", 0, 1, 1),
                  ("3", "Inventaire", 0, 2, 1)),
              {"inventaire.xml": "3", "sous.xml": "2", "maitre.xml": "1"})
    assert g.parent_of("inventaire.xml") == "sous.xml"
    assert g.descendants_of("maitre.xml") == ["sous.xml", "inventaire.xml"]
    # Ordre d'indexation : les parents avant leurs fichiers rattachés.
    assert g.order() == ["maitre.xml", "sous.xml", "inventaire.xml"]


def test_missing_parent_climbs_to_nearest_present_ancestor():
    # 3 est inclus dans 2, absent du corpus, lui-même inclus dans 1 au rang 2.
    g = graph(tsv(("1", "Maître", 0, 0, 0),
                  ("2", "Absent", 0, 1, 2),
                  ("3", "Orphelin", 0, 2, 1),
                  ("4", "Volume", 0, 1, 1),
                  ("5", "Dernier", 0, 1, 3)),
              {"maitre.xml": "1", "orphelin.xml": "3", "volume.xml": "4", "dernier.xml": "5"})
    assert g.parent_of("orphelin.xml") == "maitre.xml"
    # À la place du parent manquant (rang 2).
    assert g.children_of("maitre.xml") == ["volume.xml", "orphelin.xml", "dernier.xml"]


# ---------------------------------------------------------------------------
# Succession
# ---------------------------------------------------------------------------

def test_succession_chain_comes_right_after_its_predecessor():
    g = graph(tsv(("1", "Maître", 0, 0, 0),
                  ("2", "Volume 1", 0, 1, 1),
                  ("3", "Volume 1 suite", 2, 0, 0),
                  ("4", "Volume 1 suite 2", 3, 0, 0),
                  ("5", "Volume 2", 0, 1, 2)),
              {"maitre.xml": "1", "v1.xml": "2", "v1s.xml": "3", "v1s2.xml": "4", "v2.xml": "5"})
    # Même parent que le premier de la chaîne, avant le frère suivant de celui-ci.
    assert g.children_of("maitre.xml") == ["v1.xml", "v1s.xml", "v1s2.xml", "v2.xml"]
    assert g.parent_of("v1s2.xml") == "maitre.xml"


def test_several_successors_of_the_same_file():
    # Cas réel (631139801-5A/5B/5C) : trois fichiers déclarent le même précédent.
    g = graph(tsv(("1", "Maître", 0, 0, 0),
                  ("2", "Archives 5", 0, 1, 5),
                  ("4300", "Archives 5C", 2, 0, 0),
                  ("4309", "Archives 5B", 2, 0, 0),
                  ("4682", "Archives 5A", 2, 0, 0),
                  ("6", "Archives 6", 0, 1, 6)),
              {"maitre.xml": "1", "5.xml": "2", "5c.xml": "4300", "5b.xml": "4309",
               "5a.xml": "4682", "6.xml": "6"})
    assert g.children_of("maitre.xml") == ["5.xml", "5a.xml", "5b.xml", "5c.xml", "6.xml"]


def test_successor_of_a_top_level_file_stays_top_level():
    g = graph(tsv(("1", "Fonds", 0, 0, 0),
                  ("2", "Fonds suite", 1, 0, 0),
                  ("3", "Autre fonds", 0, 0, 1)),
              {"fonds.xml": "1", "suite.xml": "2", "autre.xml": "3"})
    assert g.parent_of("suite.xml") is None
    assert g.children_of(None) == ["fonds.xml", "suite.xml", "autre.xml"]


def test_successor_of_a_missing_file_keeps_its_place():
    # 3 suit 2, absent du corpus mais inclus dans 1 au rang 1.
    g = graph(tsv(("1", "Maître", 0, 0, 0),
                  ("2", "Absent", 0, 1, 1),
                  ("3", "Suite de l'absent", 2, 0, 0),
                  ("4", "Volume", 0, 1, 2)),
              {"maitre.xml": "1", "suite.xml": "3", "volume.xml": "4"})
    assert g.children_of("maitre.xml") == ["suite.xml", "volume.xml"]


def test_successor_of_an_included_file_with_its_own_inclusions():
    # Inclusion et succession combinées : le successeur a lui-même des fichiers inclus.
    g = graph(tsv(("1", "Maître", 0, 0, 0),
                  ("2", "Partie 1", 0, 1, 1),
                  ("3", "Partie 2", 2, 0, 0),
                  ("4", "Partie 2, annexe", 0, 3, 1)),
              {"maitre.xml": "1", "p1.xml": "2", "p2.xml": "3", "annexe.xml": "4"})
    assert g.children_of("maitre.xml") == ["p1.xml", "p2.xml"]
    assert g.children_of("p2.xml") == ["annexe.xml"]
    assert g.order() == ["maitre.xml", "p1.xml", "p2.xml", "annexe.xml"]


# ---------------------------------------------------------------------------
# Identification des fichiers et cas dégradés
# ---------------------------------------------------------------------------

def test_file_known_by_url_only_follows_the_file_holding_its_fileid():
    # @url donne le FileId du premier fichier de la chaîne (cas réel 751079801-01a/01b/01d).
    lia = parse_liaisons(tsv(("1", "Maître", 0, 0, 0), ("2", "01a", 0, 1, 1), ("3", "Suivant", 0, 1, 2)))
    g = FileGraph(lia, {"maitre.xml": ("1", False), "01a.xml": ("2", True), "01b.xml": ("2", True),
                        "01d.xml": ("2", True), "suivant.xml": ("3", False)})
    assert g.children_of("maitre.xml") == ["01a.xml", "01b.xml", "01d.xml", "suivant.xml"]


def test_files_without_liaison_stand_alone_after_linked_ones():
    g = graph(tsv(("1", "Maître", 0, 0, 0), ("2", "Volume", 0, 1, 1)),
              {"maitre.xml": "1", "volume.xml": "2", "isole.xml": "99"})
    assert g.parent_of("isole.xml") is None
    assert g.children_of(None) == ["maitre.xml", "isole.xml"]


def test_cycle_does_not_loop():
    g = graph(tsv(("1", "X", 0, 2, 1), ("2", "Y", 0, 1, 1)), {"x.xml": "1", "y.xml": "2"})
    assert sorted(g.order()) == ["x.xml", "y.xml"]
    assert g.children_of(None)


def test_parse_liaisons_raw_and_xml_wrapped():
    raw = tsv(("9", "Fichier", 8, 0, 3))
    wrapped = f'<?xml version="1.0" encoding="utf-8"?><fichier nom="liaisons.tsv"><contenu>{raw}</contenu></fichier>'
    for text in (raw, wrapped):
        lia = parse_liaisons(text)["9"]
        assert (lia.previous, lia.parent, lia.rank) == ("8", "", 3)


def test_file_id_of(tmp_path: Path):
    def eadid(attrs: str, text: str = "") -> Path:
        p = tmp_path / "f.xml"
        p.write_text(f"<ead><eadheader><eadid {attrs}>{text}</eadid></eadheader></ead>", encoding="utf-8")
        return p

    url = 'url="https://calames.abes.fr/pub/ms/FileId-5279"'
    assert file_id_of(eadid(f'identifier="FR-1_CALAMESFileId-4910" {url}')) == ("4910", False)
    assert file_id_of(eadid(url, "FR-1_CALAMESFileId-4911_Fonds")) == ("4911", False)
    assert file_id_of(eadid(url)) == ("5279", True)
    assert file_id_of(eadid('identifier="sans-fileid"')) is None
