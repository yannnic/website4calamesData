"""
Moissonnage OAI-PMH de Calames — format oai_ead.

Récupère les instruments de recherche EAD depuis :
    https://calames.abes.fr/oai/oai2.aspx

Usage :
    python harvester.py [--out DIR] [--from DATE] [--set SET]
                        [--limit N] [--delay SECS] [--dry-run]

Options :
    --out DIR       Répertoire de sortie des fichiers XML  (défaut : ../../data/calames)
    --from DATE     Ne moissonne que les notices modifiées depuis DATE (YYYY-MM-DD)
    --set SET       Restreint au setSpec donné (ex. : 751059803)
    --limit N       S'arrête après N notices (utile pour tester)
    --delay SECS    Délai entre requêtes en secondes              (défaut : 1.0)
    --dry-run       Liste les identifiants sans télécharger les fichiers
    --state FILE    Fichier JSON pour mémoriser la date du dernier moissonnage
                    (défaut : harvester_state.json dans --out)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urlencode

import requests
from lxml import etree

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL   = "https://calames.abes.fr/oai/oai2.aspx"
PREFIX     = "oai_ead"
OAI_NS     = "http://www.openarchives.org/OAI/2.0/"
USER_AGENT = "CalamesHarvester/1.0 (contact: voir CLAUDE.md)"


# ---------------------------------------------------------------------------
# Helpers HTTP
# ---------------------------------------------------------------------------

def _get(params: dict, delay: float, session: requests.Session) -> etree._Element:
    """Effectue une requête OAI-PMH et retourne l'élément racine XML."""
    url = BASE_URL + "?" + urlencode(params)
    resp = session.get(url, timeout=60)
    resp.raise_for_status()
    time.sleep(delay)
    root = etree.fromstring(resp.content)
    _check_oai_error(root)
    return root


def _check_oai_error(root: etree._Element) -> None:
    err = root.find(f"{{{OAI_NS}}}error")
    if err is not None:
        code = err.get("code", "")
        msg  = (err.text or "").strip()
        raise RuntimeError(f"OAI erreur [{code}] : {msg}")


# ---------------------------------------------------------------------------
# ListIdentifiers avec pagination
# ---------------------------------------------------------------------------

def list_identifiers(
    from_date: Optional[str],
    set_spec:  Optional[str],
    delay:     float,
    session:   requests.Session,
) -> Iterator[tuple[str, str]]:
    """
    Génère des tuples (identifier, datestamp) pour tous les enregistrements
    disponibles en format oai_ead.
    """
    params: dict = {"verb": "ListIdentifiers", "metadataPrefix": PREFIX}
    if from_date:
        params["from"] = from_date
    if set_spec:
        params["set"] = set_spec

    page = 0
    while True:
        page += 1
        root = _get(params, delay, session)
        li   = root.find(f"{{{OAI_NS}}}ListIdentifiers")
        if li is None:
            break

        for header in li.findall(f"{{{OAI_NS}}}header"):
            if header.get("status") == "deleted":
                continue
            identifier = header.findtext(f"{{{OAI_NS}}}identifier") or ""
            datestamp  = header.findtext(f"{{{OAI_NS}}}datestamp")  or ""
            if identifier:
                yield identifier, datestamp

        token_el = li.find(f"{{{OAI_NS}}}resumptionToken")
        if token_el is None or not (token_el.text or "").strip():
            break
        params = {"verb": "ListIdentifiers", "resumptionToken": token_el.text.strip()}

        # Progression
        cursor      = token_el.get("cursor")
        complete_ls = token_el.get("completeListSize")
        if cursor and complete_ls:
            print(f"  page {page} — {cursor}/{complete_ls} identifiants récupérés…", flush=True)


# ---------------------------------------------------------------------------
# GetRecord → contenu EAD brut
# ---------------------------------------------------------------------------

def _copy_without_ns(el: etree._Element) -> etree._Element:
    """
    Reconstruit récursivement un élément sans aucun namespace.
    Nécessaire car lxml hérite le namespace OAI-PMH dans le contenu <metadata>.
    """
    local = el.tag.split("}", 1)[1] if "}" in el.tag else el.tag
    new_el = etree.Element(local)
    for k, v in el.attrib.items():
        new_el.set(k.split("}", 1)[1] if "}" in k else k, v)
    new_el.text = el.text
    new_el.tail = None  # tail appartient au parent, pas à cet élément
    for child in el:
        new_child = _copy_without_ns(child)
        new_child.tail = child.tail
        new_el.append(new_child)
    return new_el


def get_ead(identifier: str, delay: float, session: requests.Session) -> Optional[bytes]:
    """
    Récupère le contenu EAD d'un enregistrement et le retourne comme bytes UTF-8.
    Retourne None si le contenu est vide ou absent.
    """
    params = {
        "verb": "GetRecord",
        "metadataPrefix": PREFIX,
        "identifier": identifier,
    }
    root = _get(params, delay, session)
    record   = root.find(f".//{{{OAI_NS}}}record")
    if record is None:
        return None
    metadata = record.find(f"{{{OAI_NS}}}metadata")
    if metadata is None or len(metadata) == 0:
        return None

    # Le premier enfant de <metadata> est l'élément <ead>.
    # On reconstruit l'arbre sans les namespaces hérités du wrapper OAI-PMH.
    ead_el = _copy_without_ns(metadata[0])
    xml_bytes = etree.tostring(
        ead_el,
        encoding="unicode",
        xml_declaration=False,
        pretty_print=True,
    ).encode("utf-8")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes


# ---------------------------------------------------------------------------
# Nom de fichier à partir de l'eadid
# ---------------------------------------------------------------------------

def _filename_from_ead(content: bytes, identifier: str) -> str:
    """
    Extrait l'eadid du contenu EAD pour nommer le fichier.
    Repli sur l'identifiant OAI nettoyé si absent.
    """
    try:
        root   = etree.fromstring(content)
        eadid  = root.find(".//{*}eadid")
        if eadid is not None and eadid.text:
            text = eadid.text.strip()
            # Garde uniquement les caractères sûrs pour un nom de fichier
            safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in text)
            if safe:
                return safe + ".xml"
    except Exception:
        pass
    # Repli : "oai:oaicalames.abes.fr:123" → "oai_calames_123.xml"
    safe = identifier.replace(":", "_").replace("/", "_")
    return safe + ".xml"


# ---------------------------------------------------------------------------
# Moissonnage principal
# ---------------------------------------------------------------------------

def harvest(
    out_dir:   Path,
    from_date: Optional[str],
    set_spec:  Optional[str],
    limit:     Optional[int],
    delay:     float,
    dry_run:   bool,
    state_file: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    print(f"Moissonnage de {BASE_URL}")
    print(f"Format : {PREFIX}  |  from : {from_date or '(tout)'}  |  set : {set_spec or '(tous)'}")
    if dry_run:
        print("Mode dry-run : les fichiers ne seront pas écrits.")
    print()

    total_seen = total_new = total_skip = total_err = 0
    harvest_start = time.strftime("%Y-%m-%d")

    try:
        for identifier, datestamp in list_identifiers(from_date, set_spec, delay, session):
            total_seen += 1
            if limit and total_seen > limit:
                print(f"Limite de {limit} notices atteinte.")
                break

            if dry_run:
                print(f"  [DRY] {identifier}  ({datestamp})")
                total_new += 1
                continue

            # Tentative de récupération
            try:
                content = get_ead(identifier, delay, session)
            except Exception as exc:
                print(f"  ERREUR {identifier} : {exc}", file=sys.stderr)
                total_err += 1
                continue

            if not content:
                print(f"  VIDE  {identifier}", file=sys.stderr)
                total_skip += 1
                continue

            filename  = _filename_from_ead(content, identifier)
            dest      = out_dir / filename
            dest.write_bytes(content)
            total_new += 1
            print(f"  OK  {filename}  ({datestamp})")

    except KeyboardInterrupt:
        print("\nInterrompu par l'utilisateur.")

    print()
    print(f"Terminé. {total_seen} vus, {total_new} fichiers écrits, "
          f"{total_skip} vides, {total_err} erreurs.")

    # Met à jour l'état si pas de dry-run
    if not dry_run and total_new > 0:
        state = {"last_harvest": harvest_start}
        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(f"État mis à jour : {state_file}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    default_out = Path(__file__).parent.parent.parent / "data" / "calames"

    parser = argparse.ArgumentParser(
        description="Moissonne les EAD de Calames via OAI-PMH.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--out",   default=str(default_out),
                        help="Répertoire de sortie (défaut : ../../data)")
    parser.add_argument("--from",  dest="from_date", default=None,
                        metavar="DATE",
                        help="Date de début YYYY-MM-DD (notices modifiées depuis)")
    parser.add_argument("--set",   default=None,
                        metavar="SET",
                        help="SetSpec OAI (ex. : 751059803)")
    parser.add_argument("--limit", type=int, default=None,
                        metavar="N",
                        help="Nombre maximum de notices à traiter")
    parser.add_argument("--delay", type=float, default=1.0,
                        metavar="SECS",
                        help="Délai entre requêtes en secondes (défaut : 1.0)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Liste les identifiants sans télécharger")
    parser.add_argument("--incremental", action="store_true",
                        help="Utilise la date du dernier moissonnage comme --from")
    parser.add_argument("--state", default=None,
                        metavar="FILE",
                        help="Fichier d'état JSON (défaut : harvester_state.json dans --out)")

    args = parser.parse_args()
    out_dir    = Path(args.out)
    state_file = Path(args.state) if args.state else out_dir / "harvester_state.json"

    from_date = args.from_date
    if args.incremental and not from_date:
        if state_file.exists():
            state     = json.loads(state_file.read_text(encoding="utf-8"))
            from_date = state.get("last_harvest")
            if from_date:
                print(f"Mode incrémental : from={from_date} (dernier moissonnage)")
        else:
            print("Mode incrémental : aucun état trouvé, moissonnage complet.")

    harvest(
        out_dir    = out_dir,
        from_date  = from_date,
        set_spec   = args.set,
        limit      = args.limit,
        delay      = args.delay,
        dry_run    = args.dry_run,
        state_file = state_file,
    )


if __name__ == "__main__":
    main()
