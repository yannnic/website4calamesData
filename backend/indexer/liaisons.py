"""
Liaisons between EAD files (Calames liaisons.tsv).

Large inventories are split into several EAD files which Calames reassembles
into a single hierarchy:
  - inclusion  : a file is attached under the root (archdesc) of a parent file,
                 at a given rank among the parent's attached files;
  - succession : a file comes right after another one, under the same parent.

liaisons.tsv has one line per file (tab-separated, no header):

    FileId  label  admin_path  flag  previous_FileId  parent_FileId  rank

previous_FileId / parent_FileId are 0 (or empty) when absent. A file is matched
to its line through the FileId found in its <eadid>: @identifier or text
("..._CALAMESFileId-4752"), else @url (".../FileId-4752"). The url may give the
FileId of the first file of a succession chain: a file known by its url only,
whose FileId is held by another file, is placed right after that file.

The harvester downloads liaisons.tsv next to the EAD files (harvester.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

LIAISONS_FILE = "liaisons.tsv"

_FILE_ID_RE = re.compile(r"FileId-(\d+)")


@dataclass(frozen=True)
class Liaison:
    file_id: str
    label: str
    previous: str   # FileId of the preceding file ("" if none)
    parent: str     # FileId of the parent file ("" if none)
    rank: int       # rank among the parent's attached files


def _ref(value: str) -> str:
    value = value.strip()
    return "" if value in ("", "0") else value


def parse_liaisons(text: str) -> dict[str, Liaison]:
    """Parse liaisons.tsv content, raw or wrapped in the XML of lstfiles.aspx."""
    if text.lstrip().startswith("<"):
        root = etree.fromstring(text.encode("utf-8"))
        text = root.findtext(".//contenu") or ""
    liaisons = {}
    for line in text.splitlines():
        cols = line.rstrip("\r").split("\t")
        if len(cols) < 7 or not cols[0].strip().isdigit():
            continue
        fid = cols[0].strip()
        rank = cols[6].strip()
        liaisons[fid] = Liaison(
            file_id=fid,
            label=cols[1].strip(),
            previous=_ref(cols[4]),
            parent=_ref(cols[5]),
            rank=int(rank) if rank.isdigit() else 0,
        )
    return liaisons


def load_liaisons(path: Path | None) -> dict[str, Liaison]:
    """Load a liaisons file; no file means no liaisons (every file stands alone)."""
    if path is None or not path.is_file():
        return {}
    return parse_liaisons(path.read_text(encoding="utf-8-sig"))


FileRef = tuple[str, bool]   # (FileId, read from @url only)


def file_id_of(path: Path) -> FileRef | None:
    """Return the Calames FileId of an EAD file, read from its <eadid>."""
    try:
        for _, el in etree.iterparse(str(path), events=("end",), load_dtd=False,
                                     no_network=True, resolve_entities=False, recover=True):
            if etree.QName(el).localname == "eadid":
                m = _FILE_ID_RE.search(el.get("identifier", "")) or _FILE_ID_RE.search(el.text or "")
                if m:
                    return m.group(1), False
                m = _FILE_ID_RE.search(el.get("url", ""))
                return (m.group(1), True) if m else None
    except etree.XMLSyntaxError:
        pass
    return None


def _fid_key(fid: str) -> int:
    return int(fid) if fid.isdigit() else 0


class FileGraph:
    """
    Placement of the EAD files of a corpus according to the liaisons.

    Files are identified by their file name (the index's source_file). A file
    whose parent is absent from the corpus climbs to the nearest present
    ancestor, keeping its place in the order; a file without liaison stands
    alone at the top level.
    """

    def __init__(self, liaisons: dict[str, Liaison], file_ids: dict[str, FileRef | None]):
        self._liaisons = liaisons
        # Owner of each FileId: a file naming it explicitly, else (url only) the first by name.
        self._name_of: dict[str, str] = {}
        for from_url in (False, True):
            for name, ref in sorted(file_ids.items()):
                if ref and ref[1] == from_url:
                    self._name_of.setdefault(ref[0], name)
        self._parent: dict[str, str | None] = {}
        self._key: dict[str, tuple] = {}
        for name, ref in file_ids.items():
            fid = ref[0] if ref else None
            if fid not in liaisons:
                # Files without liaison come after the linked ones, by name.
                self._parent[name], self._key[name] = None, (1, name)
                continue
            parent_fid, key = self._place(fid, set())
            if self._name_of[fid] != name:
                # Shares the FileId of another file: comes right after it.
                key += (0, name.casefold(), 0)
            self._parent[name] = self._name_of.get(parent_fid) if parent_fid else None
            self._key[name] = (0,) + key
        self._break_cycles()
        self._children: dict[str | None, list[str]] = {}
        for name in sorted(self._parent, key=lambda n: self._key[n]):
            self._children.setdefault(self._parent[name], []).append(name)

    def _own_key(self, lia: Liaison) -> tuple:
        return (lia.rank, lia.label.casefold(), _fid_key(lia.file_id))

    def _place(self, fid: str, seen: set[str]) -> tuple[str | None, tuple]:
        """(present parent FileId or None, sort key under that parent)."""
        lia = self._liaisons.get(fid)
        if lia is None or fid in seen:
            return None, ()
        seen.add(fid)
        if lia.parent:
            if lia.parent in self._name_of:
                return lia.parent, self._own_key(lia)
            parent_fid, key = self._place(lia.parent, seen)
            return parent_fid, key + self._own_key(lia)
        if lia.previous:
            # Right after the previous file: its key is a prefix of ours.
            parent_fid, key = self._place(lia.previous, seen)
            return parent_fid, key + self._own_key(lia)
        return None, self._own_key(lia)

    def _break_cycles(self) -> None:
        for name in self._parent:
            seen = {name}
            p = self._parent[name]
            while p is not None:
                if p in seen:
                    self._parent[name] = None
                    break
                seen.add(p)
                p = self._parent[p]

    def parent_of(self, name: str) -> str | None:
        return self._parent.get(name)

    def children_of(self, name: str | None) -> list[str]:
        """Files attached under `name` (None: top-level files), in display order."""
        return self._children.get(name, [])

    def descendants_of(self, name: str) -> list[str]:
        """Every file below `name`, parents before children."""
        out = []
        for child in self.children_of(name):
            out.append(child)
            out.extend(self.descendants_of(child))
        return out

    def order(self) -> list[str]:
        """All files, parents before children (indexing order)."""
        out = []
        for top in self.children_of(None):
            out.append(top)
            out.extend(self.descendants_of(top))
        return out

    def __contains__(self, name: str) -> bool:
        return name in self._parent

