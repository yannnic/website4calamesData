"""
EAD watcher — surveille un dossier et maintient l'index MeiliSearch à jour.

Toutes les POLL_INTERVAL secondes, compare le contenu du dossier à l'état connu :
  - fichier nouveau ou modifié  → (ré)indexé
  - fichier supprimé            → ses documents sont retirés de l'index

Un fichier n'est traité que lorsque sa taille et sa date de modification sont
stables entre deux passages (évite d'indexer un dépôt SFTP en cours d'écriture).

L'état (mtime, taille, statut, erreur éventuelle) est écrit dans STATE_FILE,
lu par l'API pour afficher le statut des fichiers déposés.

Au premier démarrage, si EAD_DIR ne contient aucun .xml et que SEED_DIR est
défini, les fichiers de SEED_DIR y sont copiés (jeu de démonstration).

Variables d'environnement :
    EAD_DIR        dossier surveillé                 (défaut : /data/ead)
    SEED_DIR       dossier du jeu de démonstration   (optionnel)
    STATE_FILE     fichier d'état JSON               (défaut : /state/watcher.json)
    MEILI_HOST, MEILI_KEY, MEILI_INDEX
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

import meilisearch

from indexer import ensure_index, index_file, remove_file

EAD_DIR       = Path(os.getenv("EAD_DIR", "/data/ead"))
SEED_DIR      = os.getenv("SEED_DIR")
STATE_FILE    = Path(os.getenv("STATE_FILE", "/state/watcher.json"))
MEILI_HOST    = os.getenv("MEILI_HOST", "http://localhost:7700")
MEILI_KEY     = os.getenv("MEILI_KEY", "")
MEILI_INDEX   = os.getenv("MEILI_INDEX", "ead_components")
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


def seed_if_empty() -> None:
    if not SEED_DIR or any(EAD_DIR.glob("*.xml")):
        return
    seeds = sorted(Path(SEED_DIR).glob("*.xml"))
    for p in seeds:
        shutil.copy2(p, EAD_DIR / p.name)
    if seeds:
        log(f"{len(seeds)} fichiers de démonstration copiés depuis {SEED_DIR}.")


def indexed_files(index: meilisearch.index.Index) -> set[str]:
    res = index.search("", {"limit": 0, "facets": ["source_file"]})
    return set(res.get("facetDistribution", {}).get("source_file", {}))


def connect() -> tuple[meilisearch.Client, meilisearch.index.Index]:
    client = meilisearch.Client(MEILI_HOST, MEILI_KEY or None)
    while True:
        try:
            client.health()
            return client, ensure_index(client, MEILI_INDEX)
        except Exception as exc:
            log(f"MeiliSearch indisponible ({exc}), nouvel essai dans 5 s…")
            time.sleep(5)


def main() -> None:
    EAD_DIR.mkdir(parents=True, exist_ok=True)
    seed_if_empty()
    client, index = connect()

    state = load_state()
    # Si l'index a été vidé (volume MeiliSearch recréé), l'état local ment :
    # on oublie les fichiers qui n'y figurent plus pour les réindexer.
    in_index = indexed_files(index)
    # Idem pour une indexation interrompue par un arrêt du conteneur.
    for name in list(state):
        status = state[name].get("status")
        if status == "indexing" or (status == "indexed" and name not in in_index):
            del state[name]
    # Documents orphelins : fichier absent du dossier mais présent dans l'index.
    on_disk = scan()
    for name in in_index - on_disk.keys():
        log(f"{name} : absent du dossier, retrait de l'index.")
        remove_file(client, index, name)
        state.pop(name, None)
    save_state(state)

    log(f"Surveillance de {EAD_DIR} (toutes les {POLL_INTERVAL:g} s).")
    previous: dict[str, tuple[float, int]] = {}
    while True:
        current = scan()
        changed = False

        for name, sig in sorted(current.items()):
            known = state.get(name)
            if known and (known["mtime"], known["size"]) == sig:
                continue
            if previous.get(name) != sig:
                continue  # pas encore stable : on attend le passage suivant
            state[name] = {"mtime": sig[0], "size": sig[1], "status": "indexing"}
            save_state(state)
            t0 = time.time()
            try:
                n = index_file(client, index, EAD_DIR / name)
                state[name].update(status="indexed", docs=n, error=None)
                log(f"{name} : {n} composants indexés en {time.time() - t0:.1f} s.")
            except Exception as exc:
                state[name].update(status="error", docs=0, error=str(exc))
                log(f"{name} : ERREUR {exc}")
            state[name]["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            changed = True

        for name in set(state) - current.keys():
            log(f"{name} : supprimé, retrait de l'index.")
            try:
                remove_file(client, index, name)
            except Exception as exc:
                log(f"{name} : ERREUR lors du retrait ({exc})")
                continue
            del state[name]
            changed = True

        if changed:
            save_state(state)
        previous = current
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
