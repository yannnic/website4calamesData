"""
Teste : les règles d'extraction et d'héritage du parseur EAD (dates héritées et
remontées, héritage simple et cumulatif, agents, physfacet, genreform), chacune
sur le fichier data/test correspondant ; et le commentaire de tête des fichiers de
test (file_comment), affiché dans l'interface pour le corpus de test.

    cd backend/indexer
    python -m pytest test_parser.py -v     (ou python test_parser.py)
"""

from pathlib import Path
from ead_parser import parse_ead, components_to_docs

TEST_DIR = Path(__file__).parent.parent.parent / "data" / "test"

OK  = "OK "
FAIL = "FAIL"

def check(label: str, actual, expected) -> bool:
    ok = actual == expected
    status = OK if ok else FAIL
    print(f"  [{status}] {label}")
    if not ok:
        print(f"         attendu : {expected!r}")
        print(f"         obtenu  : {actual!r}")
    # Sous pytest, seul un assert fait échouer le test.
    assert ok, f"{label} — attendu {expected!r}, obtenu {actual!r}"
    return ok


def by_id(docs: list[dict], node_id_suffix: str) -> dict:
    for d in docs:
        if d["node_id"].endswith(node_id_suffix):
            return d
    raise KeyError(f"Composant introuvable : *{node_id_suffix}")


# ---------------------------------------------------------------------------
# test_date_bottomup.xml
# ---------------------------------------------------------------------------

def test_date_bottomup():
    print("\n=== test_date_bottomup.xml ===")
    root = parse_ead(TEST_DIR / "test_date_bottomup.xml")
    docs = components_to_docs(root)

    fonds  = docs[0]
    serie_b = by_id(docs, "#serie-B")
    serie_e = by_id(docs, "#serie-E")

    check("fonds date_normal  = 1920/1985", fonds["date_normal"], "1920/1985")
    check("fonds date_start   = 1920",      fonds["date_start"],  1920)
    check("fonds date_end     = 1985",      fonds["date_end"],    1985)
    check("série-B date_normal = 1950/1985", serie_b["date_normal"], "1950/1985")
    check("série-E date_normal = 1920/1930 (inchangée)", serie_e["date_normal"], "1920/1930")


# ---------------------------------------------------------------------------
# test_date_topdown.xml
# ---------------------------------------------------------------------------

def test_date_topdown():
    print("\n=== test_date_topdown.xml ===")
    root = parse_ead(TEST_DIR / "test_date_topdown.xml")
    docs = components_to_docs(root)

    sans_date  = by_id(docs, "#dossier-sans-date")
    avec_date  = by_id(docs, "#dossier-avec-date")

    check("dossier sans date hérite 1900/2000",         sans_date["date_normal"], "1900/2000")
    check("dossier avec date garde 1955/1960",          avec_date["date_normal"], "1955/1960")


# ---------------------------------------------------------------------------
# test_subjects_cumul.xml
# ---------------------------------------------------------------------------

def test_subjects_cumul():
    print("\n=== test_subjects_cumul.xml ===")
    root = parse_ead(TEST_DIR / "test_subjects_cumul.xml")
    docs = components_to_docs(root)

    fonds   = docs[0]
    serie   = by_id(docs, "#serie-presse")
    dossier = by_id(docs, "#dossier-sport")

    check("fonds  subjects = ['Photographie']",
          fonds["subjects_norm"], ["Photographie"])
    check("série  subjects = ['Presse', 'Photographie'] (propres en premier)",
          serie["subjects_norm"], ["Presse", "Photographie"])
    check("dossier subjects = ['Sport', 'Presse', 'Photographie']",
          dossier["subjects_norm"], ["Sport", "Presse", "Photographie"])

    check("fonds  geo_names = ['Paris']",
          fonds["geo_names_norm"], ["Paris"])
    check("série  geo_names = ['Lyon', 'Paris']",
          serie["geo_names_norm"], ["Lyon", "Paris"])
    check("dossier geo_names = ['Lyon', 'Paris'] (hérité, pas de propres)",
          dossier["geo_names_norm"], ["Lyon", "Paris"])

    check("fonds  pers_names contient Dupont",
          "Dupont, Jean" in fonds["pers_names"], True)
    check("dossier pers_names contient Dupont (hérité)",
          "Dupont, Jean" in dossier["pers_names"], True)


# ---------------------------------------------------------------------------
# test_inherit_simple.xml
# ---------------------------------------------------------------------------

def test_inherit_simple():
    print("\n=== test_inherit_simple.xml ===")
    root = parse_ead(TEST_DIR / "test_inherit_simple.xml")
    docs = components_to_docs(root)

    fonds          = docs[0]
    serie          = by_id(docs, "#serie-A")
    dossier_latin  = by_id(docs, "#dossier-latin")
    dossier_normal = by_id(docs, "#dossier-normal")

    check("fonds  langue = ['fre']",           fonds["languages"],          ["fre"])
    check("série  langue héritée = ['fre']",   serie["languages"],          ["fre"])
    check("dossier-latin garde ['lat']",        dossier_latin["languages"],  ["lat"])
    check("dossier-normal hérite ['fre']",      dossier_normal["languages"], ["fre"])

    check("série  repository hérité",
          serie["repository"], "Bibliothèque de test")
    check("dossier repository hérité",
          dossier_normal["repository"], "Bibliothèque de test")

    check("série  accessrestrict hérité",
          "Communicable" in serie["access_restrict"], True)
    check("dossier accessrestrict hérité",
          "Communicable" in dossier_normal["access_restrict"], True)


# ---------------------------------------------------------------------------
# test_agents.xml
# ---------------------------------------------------------------------------

def test_agents():
    print("\n=== test_agents.xml ===")
    root = parse_ead(TEST_DIR / "test_agents.xml")
    docs = components_to_docs(root)

    fonds = docs[0]
    serie = by_id(docs, "#serie-A")

    check("fonds pers_names = ['Martin, Paul']",
          fonds["pers_names"], ["Martin, Paul"])
    check("fonds corp_names = ['Ministère de la Culture']",
          fonds["corp_names"], ["Ministère de la Culture"])
    check("fonds fam_names  = ['Famille Dupont']",
          fonds["fam_names"], ["Famille Dupont"])

    check("série pers_names = ['Durand, Marie', 'Martin, Paul'] (propre + hérité)",
          serie["pers_names"], ["Durand, Marie", "Martin, Paul"])
    check("série fam_names  = ['Famille Bernard', 'Famille Dupont'] (propre + hérité)",
          serie["fam_names"], ["Famille Bernard", "Famille Dupont"])
    check("série corp_names = ['Ministère de la Culture'] (hérité)",
          serie["corp_names"], ["Ministère de la Culture"])

    check("fonds pers_name_ids contient PPN",
          "Martin, Paul||123456789" in fonds["pers_name_ids"], True)


# ---------------------------------------------------------------------------
# test_physfacet.xml
# ---------------------------------------------------------------------------

def test_physfacet():
    print("\n=== test_physfacet.xml ===")
    root = parse_ead(TEST_DIR / "test_physfacet.xml")
    docs = components_to_docs(root)

    fonds    = docs[0]
    dossier_a = by_id(docs, "#dossier-A")
    dossier_b = by_id(docs, "#dossier-B")

    check("fonds phys_facets = ['aquarelle', 'encre']",
          fonds["phys_facets"], ["aquarelle", "encre"])
    check("fonds phys_facet_types = ['technique', 'support']",
          fonds["phys_facet_types"], ["technique", "support"])

    check("dossier-A phys_facet_types = [] (pas de physdesc)",
          dossier_a["phys_facet_types"], [])

    check("dossier-B phys_facets = ['photographie']",
          dossier_b["phys_facets"], ["photographie"])
    check("dossier-B phys_facet_types = ['technique']",
          dossier_b["phys_facet_types"], ["technique"])


# ---------------------------------------------------------------------------
# test_genreform.xml
# ---------------------------------------------------------------------------

def test_genreform():
    print("\n=== test_genreform.xml ===")
    root = parse_ead(TEST_DIR / "test_genreform.xml")
    docs = components_to_docs(root)

    fonds  = docs[0]
    serie  = by_id(docs, "#serie-A")

    check("fonds genre_forms_norm = ['correspondance', 'manuscrit', 'aquarelle']",
          fonds["genre_forms_norm"], ["correspondance", "manuscrit", "aquarelle"])
    check("fonds gff_norm         = ['correspondance']",
          fonds["gff_norm"], ["correspondance"])
    check("fonds tdd_norm         = ['manuscrit']",
          fonds["tdd_norm"], ["manuscrit"])
    check("fonds technique_norm   = ['aquarelle']",
          fonds["technique_norm"], ["aquarelle"])

    check("série gff_norm = ['journal', 'correspondance'] (propre + hérité)",
          serie["gff_norm"], ["journal", "correspondance"])
    check("série tdd_norm hérité = ['manuscrit']",
          serie["tdd_norm"], ["manuscrit"])
    check("série technique_norm hérité = ['aquarelle']",
          serie["technique_norm"], ["aquarelle"])


# ---------------------------------------------------------------------------
# Texte non structuré (other_text) et autorités propres (*_own)
# ---------------------------------------------------------------------------

def test_other_text_and_own_authorities():
    print("\n=== other_text / *_own ===")
    docs = components_to_docs(parse_ead(TEST_DIR / "test_liaisons_maitre.xml"))
    check("other_text = <custodhist> sans son <head>", docs[0]["other_text"],
          "Don de la famille Lemarchand en 1952.")
    docs = components_to_docs(parse_ead(TEST_DIR / "test_agents.xml"))
    serie = by_id(docs, "#serie-A")
    check("série pers_names_own = sa personne seulement", serie["pers_names_own"], ["Durand, Marie"])
    check("série pers_names = propre + héritée", serie["pers_names"], ["Durand, Marie", "Martin, Paul"])
    check("série corp_names_own vide (héritée seulement)", serie["corp_names_own"], [])


# ---------------------------------------------------------------------------
# Commentaire de tête (file_comment)
# ---------------------------------------------------------------------------

def test_file_comment():
    print("\n=== file_comment ===")
    root = parse_ead(TEST_DIR / "test_liaisons_vol1.xml")
    check("commentaire de tête, indentation retirée", root.file_comment,
          "Teste : l'inclusion au rang indiqué : inclus dans le maître 9001 au rang 2, il\n"
          "vient après le volume 2 (rang 1) bien que son FileId soit plus petit.\n"
          "Voir test_liaisons_maitre.xml.")
    docs = components_to_docs(root)
    check("seulement sur le document racine", [("file_comment" in d) for d in docs],
          [True] + [False] * (len(docs) - 1))


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_date_bottomup()
    test_date_topdown()
    test_subjects_cumul()
    test_inherit_simple()
    test_agents()
    test_physfacet()
    test_genreform()
    test_other_text_and_own_authorities()
    test_file_comment()
    print("\nTerminé.")
