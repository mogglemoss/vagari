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
ESI_NAMES = "https://esi.evetech.net/latest/universe/names/"

_CLIENT_KW = dict(
    timeout=10.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True
)

_names: dict[int, str] = {}  # any ESI id → name, session cache


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
    killer: str = ""             # final blow: character or NPC faction
    killer_corp: str = ""
    killer_alliance: str = ""
    killer_ship: str = ""        # what the killer was flying


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


def _final_blow(km: dict) -> dict:
    attackers = km.get("attackers") or []
    for a in attackers:
        if a.get("final_blow"):
            return a
    return attackers[0] if attackers else {}


def kill_ids(km: dict) -> list[int]:
    """Every id on the killmail worth a name: victim hull, and the final
    blow's character (or NPC faction), corp, alliance, and hull."""
    fb = _final_blow(km)
    ids = [
        (km.get("victim") or {}).get("ship_type_id"),
        fb.get("character_id"),
        fb.get("faction_id"),
        fb.get("corporation_id"),
        fb.get("alliance_id"),
        fb.get("ship_type_id"),
    ]
    return [i for i in ids if i]


def parse_last_kill(kills: list, names: dict[int, str] | None = None) -> LastKill | None:
    """The kills feed carries full killmails inline these days; `names`
    maps the killmail's ids to display names (see kill_ids)."""
    if not kills:
        return None
    names = names or {}
    km = kills[0]
    time = None
    raw = km.get("killmail_time")
    if raw:
        try:
            time = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    fb = _final_blow(km)

    def name(key: str) -> str:
        return names.get(fb.get(key), "") if fb.get(key) else ""

    return LastKill(
        time=time,
        ship_name=names.get(
            (km.get("victim") or {}).get("ship_type_id"), "?"
        ),
        attackers=len(km.get("attackers") or []),
        isk=float((km.get("zkb") or {}).get("totalValue") or 0),
        killer=name("character_id") or name("faction_id"),
        killer_corp=name("corporation_id"),
        killer_alliance=name("alliance_id"),
        killer_ship=name("ship_type_id"),
    )


async def _resolve_names(
    client: httpx.AsyncClient, ids: list[int]
) -> dict[int, str]:
    """ESI /universe/names/: one POST covers characters, corps, alliances,
    factions, and hulls alike. Session-cached; fail-silent."""
    missing = [i for i in set(ids) if i not in _names]
    if missing:
        try:
            r = await client.post(ESI_NAMES, json=missing)
            r.raise_for_status()
            for row in r.json():
                _names[row["id"]] = row["name"]
        except Exception:
            pass
    return _names


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
                names = {}
                if kills:
                    names = await _resolve_names(client, kill_ids(kills[0]))
                last = parse_last_kill(kills, names)
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
