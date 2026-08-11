"""zKillboard system intelligence — who dies here, how often, how recently.

Two requests per system (stats + latest kill), cached for the session,
manual (`intel`) rather than automatic. Fail-silent offline. zKillboard
redirects; the client must follow or every call dies at the 3xx.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx

from vagari.enrichers.activity import USER_AGENT

ZKILL_STATS = "https://zkillboard.com/api/stats/solarSystemID/{system_id}/"
ZKILL_KILLS = "https://zkillboard.com/api/kills/solarSystemID/{system_id}/"
ESI_TYPE = "https://esi.evetech.net/latest/universe/types/{type_id}/"

_CLIENT_KW = dict(
    timeout=10.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True
)

_type_names: dict[int, str] = {}  # ship type id → name, session cache


@dataclass(frozen=True)
class SystemKillStats:
    ships_destroyed: int         # all-time
    isk_destroyed: float         # all-time, ISK
    active_characters: int       # recently active PvP characters
    active_ships: int            # distinct ship types seen recently


@dataclass(frozen=True)
class LastKill:
    time: datetime | None
    ship_name: str               # victim hull
    attackers: int
    isk: float                   # zkb totalValue


@dataclass(frozen=True)
class SystemIntel:
    stats: SystemKillStats | None
    last_kill: LastKill | None


def parse_system_stats(payload: dict) -> SystemKillStats:
    active = payload.get("activepvp") or {}

    def count(key: str) -> int:
        return int((active.get(key) or {}).get("count") or 0)

    return SystemKillStats(
        ships_destroyed=int(payload.get("shipsDestroyed") or 0),
        isk_destroyed=float(payload.get("iskDestroyed") or 0),
        active_characters=count("characters"),
        active_ships=count("ships"),
    )


def parse_last_kill(kills: list, ship_name: str = "?") -> LastKill | None:
    """The kills feed carries full killmails inline these days."""
    if not kills:
        return None
    km = kills[0]
    time = None
    raw = km.get("killmail_time")
    if raw:
        try:
            time = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return LastKill(
        time=time,
        ship_name=ship_name,
        attackers=len(km.get("attackers") or []),
        isk=float((km.get("zkb") or {}).get("totalValue") or 0),
    )


async def _ship_name(client: httpx.AsyncClient, type_id: int | None) -> str:
    if not type_id:
        return "?"
    if type_id not in _type_names:
        try:
            r = await client.get(ESI_TYPE.format(type_id=type_id))
            r.raise_for_status()
            _type_names[type_id] = r.json().get("name", "?")
        except Exception:
            return "?"
    return _type_names[type_id]


async def fetch_system_intel(system_id: int) -> SystemIntel | None:
    """Stats plus the most recent kill. None only if BOTH fail."""
    stats = last = None
    try:
        async with httpx.AsyncClient(**_CLIENT_KW) as client:
            try:
                r = await client.get(ZKILL_STATS.format(system_id=system_id))
                r.raise_for_status()
                stats = parse_system_stats(r.json())
            except Exception:
                pass
            try:
                r = await client.get(ZKILL_KILLS.format(system_id=system_id))
                r.raise_for_status()
                kills = r.json()
                ship = "?"
                if kills:
                    ship = await _ship_name(
                        client,
                        (kills[0].get("victim") or {}).get("ship_type_id"),
                    )
                last = parse_last_kill(kills, ship)
            except Exception:
                pass
    except Exception:
        return None
    if stats is None and last is None:
        return None
    return SystemIntel(stats=stats, last_kill=last)


def human_isk(value: float) -> str:
    """177408739338859 → '177.4T'."""
    for divisor, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if value >= divisor:
            return f"{value / divisor:.1f}{suffix}"
    return f"{value:.0f}"
