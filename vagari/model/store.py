"""Snapshot store: one JSON file per mutation, undo/redo as a pointer.

Layout, per chain:

    <base>/<chain-name>/snap-000042.json
    <base>/<chain-name>/HEAD              # id of the current snapshot

`commit` truncates any redo tail (snapshots newer than HEAD) and prunes the
oldest snapshots beyond `keep`.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from vagari.model.chain import Chain

_SNAP = re.compile(r"^snap-(\d{6})\.json$")


def default_base_dir(app_name: str = "vagari") -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name / "state"
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(root) / app_name / "state"
    root = os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
    return Path(root) / app_name


class Store:
    def __init__(self, base_dir: Path | None = None, *, keep: int = 100):
        self.base_dir = base_dir or default_base_dir()
        self.keep = keep

    # -- internals -----------------------------------------------------------

    def _chain_dir(self, name: str) -> Path:
        d = self.base_dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _snapshots(self, name: str) -> list[int]:
        ids = []
        for p in self._chain_dir(name).iterdir():
            m = _SNAP.match(p.name)
            if m:
                ids.append(int(m.group(1)))
        return sorted(ids)

    def _path(self, name: str, snap_id: int) -> Path:
        return self._chain_dir(name) / f"snap-{snap_id:06d}.json"

    def _head(self, name: str) -> int | None:
        head_file = self._chain_dir(name) / "HEAD"
        if not head_file.exists():
            return None
        try:
            return int(head_file.read_text().strip())
        except ValueError:
            return None

    def _set_head(self, name: str, snap_id: int) -> None:
        (self._chain_dir(name) / "HEAD").write_text(str(snap_id))

    def _load(self, name: str, snap_id: int) -> Chain:
        return Chain.from_dict(json.loads(self._path(name, snap_id).read_text()))

    # -- public API ----------------------------------------------------------

    def commit(self, chain: Chain) -> int:
        """Persist a snapshot of the chain and return its id."""
        name = chain.name
        snaps = self._snapshots(name)
        head = self._head(name)

        # A commit after undo discards the redo tail.
        if head is not None:
            for snap_id in snaps:
                if snap_id > head:
                    self._path(name, snap_id).unlink()
            snaps = [s for s in snaps if s <= head]

        snap_id = (snaps[-1] + 1) if snaps else 1
        self._path(name, snap_id).write_text(json.dumps(chain.to_dict(), indent=1))
        self._set_head(name, snap_id)

        snaps.append(snap_id)
        for old in snaps[: -self.keep]:
            self._path(name, old).unlink()
        return snap_id

    def amend(self, chain: Chain) -> int:
        """Overwrite the current head snapshot instead of creating a new one.

        Used for location-only changes (nav, follow-me): a pilot roaming 30
        jumps should not burn 30 undo slots.
        """
        head = self._head(chain.name)
        if head is None or not self._path(chain.name, head).exists():
            return self.commit(chain)
        self._path(chain.name, head).write_text(json.dumps(chain.to_dict(), indent=1))
        return head

    def undo(self, name: str) -> Chain | None:
        head = self._head(name)
        if head is None:
            return None
        older = [s for s in self._snapshots(name) if s < head]
        if not older:
            return None
        self._set_head(name, older[-1])
        return self._load(name, older[-1])

    def redo(self, name: str) -> Chain | None:
        head = self._head(name)
        if head is None:
            return None
        newer = [s for s in self._snapshots(name) if s > head]
        if not newer:
            return None
        self._set_head(name, newer[0])
        return self._load(name, newer[0])

    def load_latest(self, name: str) -> Chain | None:
        head = self._head(name)
        if head is not None and self._path(name, head).exists():
            return self._load(name, head)
        snaps = self._snapshots(name)
        if not snaps:
            return None
        self._set_head(name, snaps[-1])
        return self._load(name, snaps[-1])

    # -- follow-me pilot lock (app-level, survives restarts) -----------------

    def load_pilot(self) -> str | None:
        f = self.base_dir / "PILOT"
        try:
            return f.read_text().strip() or None
        except OSError:
            return None

    def save_pilot(self, pilot: str | None) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        f = self.base_dir / "PILOT"
        if pilot:
            f.write_text(pilot)
        else:
            f.unlink(missing_ok=True)

    def load_trail(self) -> tuple[list, list] | None:
        """The unfiled-jump trail: (names, anchor path) — survives restarts."""
        import json

        f = self.base_dir / "TRAIL"
        try:
            d = json.loads(f.read_text())
            return list(d["names"]), list(d["from"])
        except (OSError, ValueError, KeyError):
            return None

    def save_trail(self, names: list, from_path: list | None) -> None:
        import json

        self.base_dir.mkdir(parents=True, exist_ok=True)
        f = self.base_dir / "TRAIL"
        if names and from_path is not None:
            f.write_text(json.dumps({"names": names, "from": from_path}))
        else:
            f.unlink(missing_ok=True)

    def load_active(self) -> str | None:
        try:
            return (self.base_dir / "ACTIVE").read_text().strip() or None
        except OSError:
            return None

    def save_active(self, name: str) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "ACTIVE").write_text(name)

    def load_orientation(self) -> int:
        """0..2 = next hint due; 3 = oriented, never hint again."""
        try:
            return int((self.base_dir / "ORIENTED").read_text().strip())
        except (OSError, ValueError):
            return 0

    def save_orientation(self, stage: int) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "ORIENTED").write_text(str(stage))

    def chains(self) -> list[str]:
        if not self.base_dir.exists():
            return []
        return sorted(p.name for p in self.base_dir.iterdir() if p.is_dir())
