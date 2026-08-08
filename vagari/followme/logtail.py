"""EVE chatlog tailer — follows pilots via Local channel changes.

EVE writes UTF-16LE chatlogs to Documents/EVE/logs/Chatlogs, one Local file
per character session (`Local_YYYYMMDD_HHMMSS_<charID>.txt`), naming the
pilot in the header (`Listener: <name>`). Jumping systems appends:

    [ 2026.08.08 21:07:31 ] EVE System > Channel changed to Local : Jita

Multiboxing means several files are live at once, and chat spam in a trade
hub bumps mtimes constantly — so "follow the newest file" follows the wrong
pilot. This tailer watches EVERY active Local file concurrently and tags
each event with its pilot; the session layer decides whom to follow.

On first sight of a file we emit only its LAST system change, marked
initial=True (the pilot's current position, not a live jump).
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

_LOG_RE = re.compile(r"\[ (\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}) \] (.+?) > (.*)")
_SYSTEM_CHANGED = "Channel changed to Local :"
_LISTENER = "Listener:"

# Only files touched this recently are tailed — old sessions are history.
ACTIVE_WINDOW_HOURS = 48

LOG_CANDIDATES: list[Path] = [
    Path.home() / "Documents" / "EVE" / "logs" / "Chatlogs",
    # Windows commonly redirects Documents into OneDrive.
    Path.home() / "OneDrive" / "Documents" / "EVE" / "logs" / "Chatlogs",
    Path.home() / ".local" / "share" / "Steam" / "steamapps" / "compatdata" / "8500"
    / "pfx" / "drive_c" / "users" / "steamuser" / "My Documents" / "EVE" / "logs"
    / "Chatlogs",
    Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam"
    / "steamapps" / "compatdata" / "8500" / "pfx" / "drive_c" / "users" / "steamuser"
    / "My Documents" / "EVE" / "logs" / "Chatlogs",
]


def detect_chatlog_dir() -> Path | None:
    """VAGARI_LOG_DIR overrides; otherwise first existing candidate."""
    override = os.environ.get("VAGARI_LOG_DIR")
    if override:
        p = Path(override).expanduser()
        return p if p.is_dir() else None
    for p in LOG_CANDIDATES:
        if p.is_dir():
            return p
    return None


@dataclass(frozen=True)
class LocalEvent:
    pilot: str        # listener name, or "#<charID>" if the header is absent
    system: str
    initial: bool     # replayed position on first sight, not a live jump


def parse_system_change(line: str) -> str | None:
    """System name if the line is a Local channel change, else None."""
    m = _LOG_RE.match(line.strip().lstrip("﻿"))
    if not m:
        return None
    sender, message = m.group(2), m.group(3)
    if sender == "EVE System" and _SYSTEM_CHANGED in message:
        return message.split(":", 1)[1].strip() or None
    return None


def _pilot_from_filename(path: Path) -> str:
    # Local_20260808_210726_95660042.txt → "#95660042"
    stem_parts = path.stem.split("_")
    return f"#{stem_parts[-1]}" if len(stem_parts) >= 4 else path.stem


def parse_listener(text: str) -> str | None:
    """Pilot name from a chatlog header."""
    for line in text.splitlines()[:20]:
        line = line.strip().lstrip("﻿")
        if line.startswith(_LISTENER):
            return line[len(_LISTENER):].strip() or None
    return None


class _Tailed:
    def __init__(self, path: Path):
        self.path = path
        self.handle = open(path, encoding="utf-16-le", errors="replace")
        existing = self.handle.read()
        self.position = self.handle.tell()
        self.pilot = parse_listener(existing) or _pilot_from_filename(path)
        self.last_known: str | None = None
        for line in existing.splitlines():
            name = parse_system_change(line)
            if name:
                self.last_known = name

    def read_new(self) -> list[str]:
        self.handle.seek(self.position)
        data = self.handle.read()
        if not data:
            return []
        self.position = self.handle.tell()
        return [n for n in map(parse_system_change, data.splitlines()) if n]

    def close(self) -> None:
        self.handle.close()


def _active_logs(chatlog_dir: Path) -> list[Path]:
    cutoff = time.time() - ACTIVE_WINDOW_HOURS * 3600
    try:
        return [
            p for p in chatlog_dir.glob("Local_*.txt") if p.stat().st_mtime >= cutoff
        ]
    except OSError:
        return []


async def tail_local_files(
    chatlog_dir: Path,
    on_event: Callable[[LocalEvent], Awaitable[None]],
    poll_interval: float = 1.0,
) -> None:
    """Stream LocalEvents from every active Local chatlog. Runs until cancelled."""
    tailed: dict[Path, _Tailed] = {}
    try:
        while True:
            active = set(_active_logs(chatlog_dir))

            for path in sorted(active - tailed.keys()):
                try:
                    t = _Tailed(path)
                except OSError:
                    continue
                tailed[path] = t
                if t.last_known:
                    await on_event(LocalEvent(t.pilot, t.last_known, initial=True))

            for path in list(tailed.keys() - active):
                tailed.pop(path).close()

            for t in list(tailed.values()):
                try:
                    systems = t.read_new()
                except OSError:
                    tailed.pop(t.path, None)
                    t.close()
                    continue
                for name in systems:
                    await on_event(LocalEvent(t.pilot, name, initial=False))

            await asyncio.sleep(poll_interval)
    except asyncio.CancelledError:
        pass
    finally:
        for t in tailed.values():
            t.close()
