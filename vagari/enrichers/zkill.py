"""zKillboard system statistics — who dies here, and how often.

One request per system, cached for the session, politely rate-limited by
being manual (`intel` command) rather than automatic. Fail-silent offline.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from vagari.enrichers.activity import USER_AGENT

ZKILL_STATS = "https://zkillboard.com/api/stats/solarSystemID/{system_id}/"


@dataclass(frozen=True)
class SystemKillStats:
    ships_destroyed: int         # all-time
    active_characters: int       # recent active PvP characters
    active_kills: int            # recent PvP kill count


def parse_system_stats(payload: dict) -> SystemKillStats:
    active = payload.get("activepvp") or {}

    def count(key: str) -> int:
        return int((active.get(key) or {}).get("count") or 0)

    return SystemKillStats(
        ships_destroyed=int(payload.get("shipsDestroyed") or 0),
        active_characters=count("characters"),
        active_kills=count("kills"),
    )


async def fetch_system_stats(system_id: int) -> SystemKillStats | None:
    try:
        async with httpx.AsyncClient(
            timeout=10.0, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = await client.get(ZKILL_STATS.format(system_id=system_id))
            response.raise_for_status()
            return parse_system_stats(response.json())
    except Exception:
        return None
