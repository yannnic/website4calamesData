"""
Moissonnage OAI-PMH — format oai_ead.

Récupère les instruments de recherche EAD d'un entrepôt OAI-PMH
(par défaut Calames : https://calames.abes.fr/oai/oai2.aspx).

Usage :
    python harvester.py [--url URL] [--out DIR] [--from DATE] [--set SET[,SET…]]
                        [--limit N] [--delay SECS] [--dry-run]
                        [--incremental] [--every HOURS] [--liaisons-only]

Options :
    --url URL       URL de base de l'entrepôt OAI-PMH            (env OAI_URL)
    --prefix P      metadataPrefix                   (défaut : oai_ead, env OAI_PREFIX)
    --out DIR       Répertoire de sortie des fichiers XML  (défaut : ../../data/calames)
    --from DATE     Ne moissonne que les notices modifiées depuis DATE (YYYY-MM-DD)
    --set SET       setSpec, ou liste séparée par des virgules    (env HARVEST_SETS)
    --limit N       S'arrête après N notices par set (utile pour tester) (env HARVEST_LIMIT)
    --delay SECS    Délai entre requêtes en secondes (défaut : 2, env HARVEST_DELAY)
    --dry-run       Liste les identifiants sans télécharger les fichiers
    --incremental   Utilise la date du dernier moissonnage complet comme --from
    --every HOURS   Relance un moissonnage incrémental toutes les HOURS heures
                    (0 = une seule passe, env HARVEST_EVERY_HOURS)
    --state FILE    Fichier JSON pour mémoriser la date du dernier moissonnage
                    (défaut : harvester_state.json dans --out)
    --liaisons-only Ne télécharge que liaisons.tsv

À chaque passe, liaisons.tsv (liaisons entre fichiers EAD : inclusion,
succession, cf. indexer/liaisons.py) est aussi téléchargé dans --out
(env LIAISONS_URL, vide = désactivé ; défaut : celui de Calames).

Les fichiers sont écrits de façon atomique : un service qui surveille --out
(cf. indexer/watcher.py) ne voit jamais de fichier partiel.

Une notice que le serveur refuse ou ne sait pas produire (HTTP 4xx, erreur OAI,
réponse non XML) est « rejetée » : le passage continue et la date du dernier
moissonnage avance quand même ; les notices rejetées sont listées dans --state.
Seules les vraies pannes (réseau, 5xx persistants) la bloquent.

Note : Calames déclare deletedRecord=no, les notices supprimées à la source
ne sont donc pas signalées et restent dans --out.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urlencode

import requests
from lxml import etree

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_URL = "https://calames.abes.fr/oai/oai2.aspx"
DEFAULT_LIAISONS_URL = ("https://calames.abes.fr/prod/lstfiles.aspx"
                        "?chemin=CalamesData%5Csvdata%5C&filtre=liaisons.tsv")
OAI_NS     = "http://www.openarchives.org/OAI/2.0/"
USER_AGENT = "CalamesHarvester/1.0 (contact: voir CLAUDE.md)"

# Nouvelles tentatives quand le serveur sature ou ne répond pas :
# attente delay × 2^n (plafonnée), ou Retry-After si le serveur l'indique.
MAX_RETRIES   = 6
MAX_BACKOFF   = 600   # secondes
RETRY_STATUS  = {429, 500, 502, 503, 504}
# Abandon du passage après ce nombre de notices en échec d'affilée
# (serveur indisponible : inutile d'insister notice par notice).
MAX_CONSECUTIVE_ERRORS = 5


# ---------------------------------------------------------------------------
# Helpers HTTP
# ---------------------------------------------------------------------------

def _retry_after(resp: requests.Response) -> Optional[float]:
    try:
        return float(resp.headers["Retry-After"])
    except (KeyError, ValueError):
        return None


def _get(base_url: str, params: dict, delay: float, session: requests.Session) -> etree._Element:
    """
    Effectue une requête OAI-PMH et retourne l'élément racine XML.
    Attend `delay` secondes après chaque requête ; en cas de surcharge (429/5xx)
    ou d'erreur réseau, réessaie avec un délai croissant.
    """
    url = base_url + "?" + urlencode(params)
    for attempt in range(MAX_RETRIES + 1):
        wait = None
        try:
            resp = session.get(url, timeout=120)
            if resp.status_code not in RETRY_STATUS:
                resp.raise_for_status()
                break
            wait = _retry_after(resp)
            reason = f"HTTP {resp.status_code}"
        except (requests.ConnectionError, requests.Timeout) as exc:
            reason = type(exc).__name__
        if attempt == MAX_RETRIES:
            raise RuntimeError(f"{reason} après {MAX_RETRIES} nouvelles tentatives : {url}")
        wait = min(wait or max(delay, 1.0) * 2 ** (attempt + 1), MAX_BACKOFF)
        print(f"  {reason}, nouvelle tentative dans {wait:.0f} s…", file=sys.stderr, flush=True)
        time.sleep(wait)
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
    base_url:  str,
    prefix:    str,
    from_date: Optional[str],
    set_spec:  Optional[str],
    delay:     float,
    session:   requests.Session,
) -> Iterator[tuple[str, str]]:
    """
    Génère des tuples (identifier, datestamp) pour tous les enregistrements
    disponibles en format oai_ead.
    """
    params: dict = {"verb": "ListIdentifiers", "metadataPrefix": prefix}
    if from_date:
        params["from"] = from_date
    if set_spec:
        params["set"] = set_spec

    page = 0
    while True:
        page += 1
        try:
            root = _get(base_url, params, delay, session)
        except RuntimeError as exc:
            if "noRecordsMatch" in str(exc):
                return
            raise
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
    Copie un élément en retirant tous les namespaces (balises et attributs).
    Nécessaire car lxml hérite le namespace OAI-PMH dans le contenu <metadata>.
    Les commentaires et instructions de traitement sont conservés (leur tag
    n'est pas une chaîne : une copie élément par élément échouait dessus).
    """
    copy = deepcopy(el)
    copy.tail = None  # tail appartient au parent, pas à cet élément
    for node in copy.iter():
        if not isinstance(node.tag, str):
            continue
        if "}" in node.tag:
            node.tag = node.tag.split("}", 1)[1]
        for k in [k for k in node.attrib if "}" in k]:
            node.attrib[k.split("}", 1)[1]] = node.attrib.pop(k)
    etree.cleanup_namespaces(copy)
    return copy


class RecordRejected(Exception):
    """Le serveur refuse ou ne sait pas produire cette notice ; les autres continuent."""


def get_ead(
    base_url: str, prefix: str, identifier: str, delay: float, session: requests.Session,
) -> Optional[bytes]:
    """
    Récupère le contenu EAD d'un enregistrement et le retourne comme bytes UTF-8.
    Retourne None si le contenu est vide ou absent.
    """
    params = {
        "verb": "GetRecord",
        "metadataPrefix": prefix,
        "identifier": identifier,
    }
    try:
        root = _get(base_url, params, delay, session)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        if not 400 <= status < 500:
            raise
        time.sleep(delay)
        raise RecordRejected(f"HTTP {status}") from exc
    except etree.XMLSyntaxError as exc:
        raise RecordRejected(f"réponse non XML ({exc})") from exc
    except RuntimeError as exc:
        if not str(exc).startswith("OAI erreur"):
            raise
        raise RecordRejected(str(exc)) from exc
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
    Nomme le fichier d'après l'eadid du contenu EAD, suivi de « _oai<N> »
    (N : numéro OAI de la notice, qui est son FileId Calames) sauf si l'eadid
    contient déjà ce FileId. Plusieurs notices peuvent avoir le même eadid : sans
    ce numéro, elles s'écrasaient l'une l'autre.
    Repli sur l'identifiant OAI nettoyé si l'eadid est absent.
    """
    m = re.search(r"(\d+)$", identifier)
    num = m.group(1) if m else ""
    try:
        root   = etree.fromstring(content)
        eadid  = root.find(".//{*}eadid")
        if eadid is not None and eadid.text:
            text = re.sub(r"\.xml$", "", eadid.text.strip(), flags=re.I)
            # Garde uniquement les caractères sûrs pour un nom de fichier
            safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in text)
            if safe:
                if num and not re.search(rf"FileId-{num}(?!\d)", safe):
                    safe += f"_oai{num}"
                return safe + ".xml"
    except Exception:
        pass
    # Repli : "oai:oaicalames.abes.fr:123" → "oai_oaicalames.abes.fr_123.xml"
    safe = identifier.replace(":", "_").replace("/", "_")
    return safe + ".xml"


# ---------------------------------------------------------------------------
# Moissonnage principal
# ---------------------------------------------------------------------------

def harvest(
    base_url:  str,
    prefix:    str,
    out_dir:   Path,
    from_date: Optional[str],
    set_specs: list[Optional[str]],
    limit:     Optional[int],
    delay:     float,
    dry_run:   bool,
    state_file: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    print(f"Moissonnage de {base_url}")
    print(f"Format : {prefix}  |  from : {from_date or '(tout)'}  |  "
          f"set : {', '.join(s for s in set_specs if s) or '(tous)'}")
    if dry_run:
        print("Mode dry-run : les fichiers ne seront pas écrits.")
    print()

    total_seen = total_new = total_skip = total_err = 0
    rejected: dict[str, str] = {}
    consecutive_err = 0
    complete = True   # False si une limite ou une interruption a tronqué la liste
    harvest_start = time.strftime("%Y-%m-%d")

    try:
        for set_spec in set_specs:
            seen_in_set = 0
            for identifier, datestamp in list_identifiers(base_url, prefix, from_date, set_spec, delay, session):
                seen_in_set += 1
                if limit and seen_in_set > limit:
                    print(f"Limite de {limit} notices atteinte.")
                    complete = False
                    break
                total_seen += 1

                if dry_run:
                    print(f"  [DRY] {identifier}  ({datestamp})")
                    total_new += 1
                    continue

                # Tentative de récupération
                try:
                    content = get_ead(base_url, prefix, identifier, delay, session)
                except RecordRejected as exc:
                    print(f"  REJET {identifier} : {exc}", file=sys.stderr)
                    rejected[identifier] = str(exc)
                    continue
                except Exception as exc:
                    print(f"  ERREUR {identifier} : {exc}", file=sys.stderr)
                    total_err += 1
                    consecutive_err += 1
                    if consecutive_err >= MAX_CONSECUTIVE_ERRORS:
                        raise RuntimeError(f"{consecutive_err} échecs consécutifs, serveur indisponible ?")
                    continue
                consecutive_err = 0

                if not content:
                    print(f"  VIDE  {identifier}", file=sys.stderr)
                    total_skip += 1
                    continue

                filename = _filename_from_ead(content, identifier)
                _write_atomic(out_dir / filename, content)
                total_new += 1
                print(f"  OK  {filename}  ({datestamp})", flush=True)

    except KeyboardInterrupt:
        print("\nInterrompu par l'utilisateur.")
        complete = False
    except (RuntimeError, requests.RequestException) as exc:
        # Échec de ListIdentifiers ou abandon : on garde ce qui a été écrit,
        # le prochain passage reprendra depuis la dernière date complète.
        print(f"\nPassage interrompu : {exc}", file=sys.stderr)
        complete = False

    print()
    print(f"Terminé. {total_seen} vus, {total_new} fichiers écrits, "
          f"{total_skip} vides, {len(rejected)} rejetées par le serveur, {total_err} erreurs.", flush=True)

    # N'avance la date que si toute la liste a été traitée sans erreur :
    # sinon le prochain passage incrémental sauterait des notices.
    if dry_run:
        return
    if complete and total_err == 0:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state = {"last_harvest": harvest_start, "url": base_url, "sets": set_specs,
                 "rejected": rejected}
        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(f"État mis à jour : {state_file}")
    else:
        print("Moissonnage incomplet : date du dernier moissonnage inchangée.")


def _write_atomic(dest: Path, content: bytes) -> None:
    tmp = dest.with_name(f".{dest.name}.part")
    tmp.write_bytes(content)
    os.replace(tmp, dest)


def fetch_liaisons(url: str, out_dir: Path) -> None:
    """
    Télécharge liaisons.tsv dans out_dir. Calames l'enveloppe dans un document
    XML (<fichier><contenu>…</contenu></fichier>) : seul le TSV est gardé.
    En cas d'échec, le fichier précédent est conservé.
    """
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120)
        resp.raise_for_status()
        content = resp.content
        if content.lstrip().startswith(b"<"):
            content = (etree.fromstring(content).findtext(".//contenu") or "").encode("utf-8")
        if not content.strip():
            raise ValueError("fichier vide")
    except Exception as exc:
        print(f"liaisons.tsv : échec du téléchargement ({exc}), fichier précédent conservé.")
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "liaisons.tsv"
    if dest.exists() and dest.read_bytes() == content:
        print("liaisons.tsv : inchangé.")
        return
    _write_atomic(dest, content)
    print(f"liaisons.tsv : {len(content.splitlines())} lignes enregistrées.")


def _load_from_date(state_file: Path, base_url: str, set_specs: list[Optional[str]]) -> Optional[str]:
    """Date du dernier moissonnage complet, si l'entrepôt et les sets n'ont pas changé."""
    if not state_file.exists():
        print("Mode incrémental : aucun état trouvé, moissonnage complet.")
        return None
    state = json.loads(state_file.read_text(encoding="utf-8"))
    if state.get("url", base_url) != base_url or state.get("sets", set_specs) != set_specs:
        print("Mode incrémental : entrepôt ou sets modifiés, moissonnage complet.")
        return None
    from_date = state.get("last_harvest")
    if from_date:
        print(f"Mode incrémental : from={from_date} (dernier moissonnage)")
    return from_date


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    default_out = Path(__file__).parent.parent.parent / "data" / "calames"
    env = os.environ.get

    parser = argparse.ArgumentParser(
        description="Moissonne des EAD via OAI-PMH (Calames par défaut).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url",   default=env("OAI_URL") or DEFAULT_URL,
                        help=f"URL de base OAI-PMH (défaut : {DEFAULT_URL})")
    parser.add_argument("--prefix", default=env("OAI_PREFIX") or "oai_ead",
                        help="metadataPrefix (défaut : oai_ead)")
    parser.add_argument("--out",   default=str(default_out),
                        help="Répertoire de sortie (défaut : ../../data/calames)")
    parser.add_argument("--from",  dest="from_date", default=None,
                        metavar="DATE",
                        help="Date de début YYYY-MM-DD (notices modifiées depuis)")
    parser.add_argument("--set",   default=env("HARVEST_SETS") or None,
                        metavar="SET",
                        help="SetSpec OAI, ou liste séparée par des virgules (ex. : 751059803,340329801)")
    parser.add_argument("--limit", type=int, default=int(env("HARVEST_LIMIT") or 0) or None,
                        metavar="N",
                        help="Nombre maximum de notices à traiter par set")
    parser.add_argument("--delay", type=float, default=float(env("HARVEST_DELAY") or 2.0),
                        metavar="SECS",
                        help="Délai entre requêtes en secondes (défaut : 2)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Liste les identifiants sans télécharger")
    parser.add_argument("--incremental", action="store_true",
                        help="Utilise la date du dernier moissonnage comme --from")
    parser.add_argument("--every", type=float, default=float(env("HARVEST_EVERY_HOURS") or 0),
                        metavar="HOURS",
                        help="Relance un moissonnage incrémental toutes les HOURS heures (0 = une passe)")
    parser.add_argument("--state", default=None,
                        metavar="FILE",
                        help="Fichier d'état JSON (défaut : harvester_state.json dans --out)")
    parser.add_argument("--liaisons-only", action="store_true",
                        help="Ne télécharge que liaisons.tsv")

    args = parser.parse_args()
    out_dir    = Path(args.out)
    state_file = Path(args.state) if args.state else out_dir / "harvester_state.json"
    set_specs  = [s.strip() for s in args.set.split(",") if s.strip()] if args.set else [None]

    liaisons_url = env("LIAISONS_URL", DEFAULT_LIAISONS_URL)
    if args.liaisons_only:
        fetch_liaisons(liaisons_url, out_dir)
        return

    while True:
        from_date = args.from_date
        if (args.incremental or args.every) and not from_date:
            from_date = _load_from_date(state_file, args.url, set_specs)

        harvest(
            base_url   = args.url,
            prefix     = args.prefix,
            out_dir    = out_dir,
            from_date  = from_date,
            set_specs  = set_specs,
            limit      = args.limit,
            delay      = args.delay,
            dry_run    = args.dry_run,
            state_file = state_file,
        )
        if liaisons_url and not args.dry_run:
            fetch_liaisons(liaisons_url, out_dir)
        if not args.every:
            break
        print(f"Prochain moissonnage dans {args.every:g} h.", flush=True)
        time.sleep(args.every * 3600)


if __name__ == "__main__":
    main()
