"""
EAD watcher — surveille un dossier et maintient l'index Elasticsearch à jour.

Toutes les POLL_INTERVAL secondes, compare le contenu du dossier à l'état connu :
  - fichier nouveau ou modifié  → (ré)indexé
  - fichier supprimé            → ses documents sont retirés de l'index

Un fichier n'est traité que lorsque sa taille et sa date de modification sont
stables entre deux passages (évite d'indexer un dépôt SFTP en cours d'écriture).

Les liaisons entre fichiers (LIAISONS_FILE, voir liaisons.py) sont suivies de la
même façon : un fichier réindexé entraîne ses fichiers rattachés (ils en
héritent), et un fichier qui change de parent (ajout, suppression, liaisons
modifiées) est réindexé sous son nouveau parent.

L'état (mtime, taille, statut, erreur éventuelle) est écrit dans STATE_FILE,
lu par l'API pour afficher le statut des fichiers déposés.

Au premier démarrage (marqueur .seeded à côté de STATE_FILE), si SEED_DIR est
défini, ses fichiers absents de EAD_DIR y sont copiés (jeu de démonstration).

Variables d'environnement :
    EAD_DIR        dossier surveillé                 (défaut : /data/ead)
    LIAISONS_FILE  liaisons entre fichiers           (défaut : EAD_DIR/liaisons.tsv)
    SEED_DIR       dossier du jeu de démonstration   (optionnel)
    STATE_FILE     fichier d'état JSON               (défaut : /state/watcher.json)
    ES_HOST, ES_USER, ES_PASSWORD, ES_INDEX
    POLL_INTERVAL  secondes entre deux passages      (défaut : 5)
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from elasticsearch import Elasticsearch

from indexer import ensure_index, index_file, make_client, remove_file, sync_attached
from liaisons import LIAISONS_FILE as _LIAISONS_NAME, FileGraph, file_id_of, load_liaisons

EAD_DIR       = Path(os.getenv("EAD_DIR", "/data/ead"))
LIAISONS_FILE = Path(os.getenv("LIAISONS_FILE", str(EAD_DIR / _LIAISONS_NAME)))
SEED_DIR      = os.getenv("SEED_DIR")
STATE_FILE    = Path(os.getenv("STATE_FILE", "/state/watcher.json"))
ES_HOST       = os.getenv("ES_HOST", "http://localhost:9200")
ES_USER       = os.getenv("ES_USER", "elastic")
ES_PASSWORD   = os.getenv("ES_PASSWORD", "")
ES_INDEX      = os.getenv("ES_INDEX", "ead_components")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "5"))


def log(msg: str) -> None:
    print(f"[watcher] {msg}", flush=True)


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, STATE_FILE)


def scan() -> dict[str, tuple[float, int]]:
    """Return {file_name: (mtime, size)} for the .xml files of EAD_DIR."""
    files = {}
    for p in EAD_DIR.glob("*.xml"):
        try:
            st = p.stat()
        except FileNotFoundError:
            continue
        files[p.name] = (st.st_mtime, st.st_size)
    return files


def liaisons_sig() -> tuple[float, int] | None:
    try:
        st = LIAISONS_FILE.stat()
    except FileNotFoundError:
        return None
    return (st.st_mtime, st.st_size)


# FileId of each file, read again only when the file changes.
_file_ids: dict[str, tuple[tuple[float, int], str | None]] = {}


def read_liaisons(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return ""


def make_graph(files: dict[str, tuple[float, int]], liaisons_path: Path = LIAISONS_FILE) -> FileGraph:
    # FileIds: for the liaisons, and indexed for the redirection of Calames URLs.
    ids = {}
    for name, sig in files.items():
        cached = _file_ids.get(name)
        if cached is None or cached[0] != sig:
            cached = _file_ids[name] = (sig, file_id_of(EAD_DIR / name))
        ids[name] = cached[1]
    return FileGraph(load_liaisons(liaisons_path), ids)


def seed_once() -> None:
    """
    Copie le jeu de démonstration au premier démarrage uniquement (marqueur dans
    le dossier d'état) : un fichier de démo supprimé ensuite n'est pas recopié.
    Un fichier déjà présent (déposé ou moissonné avant) n'est pas écrasé.
    """
    marker = STATE_FILE.parent / ".seeded"
    if not SEED_DIR or marker.exists():
        return
    copied = 0
    for p in sorted(Path(SEED_DIR).glob("*.xml")):
        dest = EAD_DIR / p.name
        if not dest.exists():
            shutil.copy2(p, dest)
            copied += 1
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    log(f"{copied} fichiers de démonstration copiés depuis {SEED_DIR}.")


def indexed_files(client: Elasticsearch) -> set[str]:
    """Return the source files present in the index (composite aggregation, paginated)."""
    files: set[str] = set()
    after = None
    while True:
        composite = {"size": 1000, "sources": [{"f": {"terms": {"field": "source_file"}}}]}
        if after:
            composite["after"] = after
        res = client.search(index=ES_INDEX, size=0, aggs={"files": {"composite": composite}})
        agg = res["aggregations"]["files"]
        files.update(b["key"]["f"] for b in agg["buckets"])
        after = agg.get("after_key")
        if not agg["buckets"] or not after:
            return files


def connect() -> Elasticsearch:
    client = make_client(ES_HOST, ES_USER, ES_PASSWORD)
    while True:
        try:
            client.cluster.health(wait_for_status="yellow", timeout="5s")
            ensure_index(client, ES_INDEX)
            return client
        except Exception as exc:
            log(f"Elasticsearch indisponible ({exc}), nouvel essai dans 5 s…")
            time.sleep(5)


def main() -> None:
    EAD_DIR.mkdir(parents=True, exist_ok=True)
    seed_once()
    client = connect()

    state = load_state()
    # Si l'index a été vidé (volume Elasticsearch recréé), l'état local ment :
    # on oublie les fichiers qui n'y figurent plus pour les réindexer.
    in_index = indexed_files(client)
    # Idem pour une indexation interrompue par un arrêt du conteneur.
    for name in list(state):
        status = state[name].get("status")
        if status == "indexing" or (status == "indexed" and name not in in_index):
            del state[name]
    # Documents orphelins : fichier absent du dossier mais présent dans l'index.
    on_disk = scan()
    orphans = in_index - on_disk.keys()
    for name in orphans:
        log(f"{name} : absent du dossier, retrait de l'index.")
        remove_file(client, ES_INDEX, name)
        state.pop(name, None)
    save_state(state)
    # Their parents (unknown here) are refreshed on the first pass.
    sync_all = bool(orphans)

    log(f"Surveillance de {EAD_DIR} (toutes les {POLL_INTERVAL:g} s).")
    # Liaisons as last applied to the index: a liaisons file changed while the
    # watcher was stopped is detected (and applied) on the first pass.
    applied = STATE_FILE.parent / "liaisons.applied.tsv"
    if not applied.exists():
        applied.write_text(read_liaisons(LIAISONS_FILE), encoding="utf-8")
    graph = make_graph({n: sig for n, sig in on_disk.items() if n in state}, applied)
    prev_lsig = liaisons_sig()
    lsig = prev_lsig if read_liaisons(applied) == read_liaisons(LIAISONS_FILE) else ("changed",)
    previous: dict[str, tuple[float, int]] = {}
    while True:
        current = scan()

        ready = []
        for name, sig in sorted(current.items()):
            known = state.get(name)
            if known and (known["mtime"], known["size"]) == sig:
                continue
            if previous.get(name) != sig:
                continue  # pas encore stable : on attend le passage suivant
            ready.append(name)
        removed = set(state) - current.keys()
        cur_lsig = liaisons_sig()
        liaisons_changed = cur_lsig != lsig and cur_lsig == prev_lsig
        prev_lsig = cur_lsig

        if ready or removed or liaisons_changed or sync_all:
            if liaisons_changed:
                log(f"{LIAISONS_FILE.name} modifié.")
                lsig = cur_lsig
            for name in sorted(removed):
                log(f"{name} : supprimé, retrait de l'index.")
                try:
                    remove_file(client, ES_INDEX, name)
                except Exception as exc:
                    log(f"{name} : ERREUR lors du retrait ({exc})")
                    continue
                del state[name]

            old_graph = graph
            graph = make_graph({n: sig for n, sig in current.items() if n in state or n in ready})
            moved = {n for n in graph.order()
                     if n in old_graph and old_graph.parent_of(n) != graph.parent_of(n)}
            done: set[str] = set()
            for name in graph.order():
                if name in done or (name not in ready and name not in moved):
                    continue
                if name in ready:
                    sig = current[name]
                    state[name] = {"mtime": sig[0], "size": sig[1], "status": "indexing"}
                    save_state(state)
                t0 = time.time()
                try:
                    counts = index_file(client, ES_INDEX, EAD_DIR / name, graph)
                    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    # Cascade: attached files are indexed too, new or modified ones included.
                    for n, docs in counts.items():
                        if n in ready:
                            sig = current[n]
                            state[n] = {"mtime": sig[0], "size": sig[1], "updated_at": now}
                        if n in state:
                            state[n].update(status="indexed", docs=docs, error=None)
                    done.update(counts)
                    extra = f" (+ {len(counts) - 1} fichiers rattachés)" if len(counts) > 1 else ""
                    log(f"{name} : {counts[name]} composants indexés{extra} en {time.time() - t0:.1f} s.")
                except Exception as exc:
                    if name in state:
                        state[name].update(status="error", docs=0, error=str(exc))
                    log(f"{name} : ERREUR {exc}")
                if name in state:
                    state[name]["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

            # Parents that gained or lost attached (or merged) files, or whose order changed.
            parents = {p for n in set(old_graph.order()) | set(graph.order())
                       for p in (old_graph.parent_of(n), graph.parent_of(n)) if p}
            for parent in sorted(parents):
                if parent in graph and (sync_all or parent in done or
                                        old_graph.children_of(parent) != graph.children_of(parent) or
                                        old_graph.successors_of(parent) != graph.successors_of(parent)):
                    try:
                        sync_attached(client, ES_INDEX, graph, parent)
                    except Exception as exc:
                        log(f"{parent} : ERREUR lors de la mise à jour des rattachements ({exc})")
            save_state(state)
            if liaisons_changed:
                applied.write_text(read_liaisons(LIAISONS_FILE), encoding="utf-8")
            sync_all = False

        previous = current
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
