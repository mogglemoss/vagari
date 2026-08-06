"""EVE chatlog tailer — follows the pilot via Local channel changes.

EVE writes UTF-16LE chatlogs to Documents/EVE/logs/Chatlogs. Jumping systems
appends:  [ 2026.08.06 12:00:00 ] EVE System > Channel changed to Local : Jita

On first open of a log file we emit only the LAST system change in existing
content (where the pilot is now) — replaying the whole history would march
the location marker through stale jumps. New lines then stream as they land.
Rotation (relog, new day) switches to the newest file automatically.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Awaitable, Callable

_LOG_RE = re.compile(r"\[ (\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}) \] (.+?) > (.*)")
_SYSTEM_CHANGED = "Channel changed to Local :"

# Candidate chatlog directories, in priority order (macOS/Windows share the
# Documents path; then Linux Steam Proton, then Steam Flatpak).
LOG_CANDIDATES: list[Path] = [
    Path.home() / "Documents" / "EVE" / "logs" / "Chatlogs",
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


def parse_system_change(line: str) -> str | None:
    """System name if the line is a Local channel change, else None."""
    m = _LOG_RE.match(line.strip().lstrip("﻿"))
    if not m:
        return None
    sender, message = m.group(2), m.group(3)
    if sender == "EVE System" and _SYSTEM_CHANGED in message:
        return message.split(":", 1)[1].strip() or None
    return None


def latest_local_log(chatlog_dir: Path) -> Path | None:
    logs = sorted(
        chatlog_dir.glob("Local_*.txt"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return logs[0] if logs else None


async def tail_system_changes(
    chatlog_dir: Path,
    on_system: Callable[[str], Awaitable[None]],
    poll_interval: float = 1.0,
) -> None:
    """Call on_system(name) for each system the pilot enters. Runs until cancelled."""
    current_path: Path | None = None
    handle = None
    position = 0

    try:
        while True:
            latest = latest_local_log(chatlog_dir)

            if latest != current_path:
                if handle:
                    handle.close()
                    handle = None
                current_path = latest
                if current_path is not None:
                    handle = open(current_path, encoding="utf-16-le", errors="replace")
                    last: str | None = None
                    for line in handle.read().splitlines():
                        name = parse_system_change(line)
                        if name:
                            last = name
                    position = handle.tell()
                    if last:
                        await on_system(last)

            if handle is not None:
                handle.seek(position)
                new_data = handle.read()
                if new_data:
                    position = handle.tell()
                    for line in new_data.splitlines():
                        name = parse_system_change(line)
                        if name:
                            await on_system(name)

            await asyncio.sleep(poll_interval)
    except asyncio.CancelledError:
        pass
    finally:
        if handle:
            handle.close()
