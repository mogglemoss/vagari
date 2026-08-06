"""System activity from ESI's public kill feed.

One unauthenticated request returns ship/pod/NPC kill counts for the last
hour across every system with activity. We map them onto J-space system ids.
Fail-silent by design: offline means no enrichment, never an error.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

ESI_SYSTEM_KILLS = "https://esi.evetech.net/latest/universe/system_kills/"
USER_AGENT = "vagari (Anoikis Cartographic Bureau; scott.corbin@gmail.com)"


@dataclass(frozen=True)
class SystemActivity:
    ship_kills: int
    pod_kills: int
    npc_kills: int

    @property
    def hostile(self) -> bool:
        """Player-versus-player activity in the last hour."""
        return self.ship_kills > 0 or self.pod_kills > 0


def parse_system_kills(payload: list[dict]) -> dict[int, SystemActivity]:
    activity: dict[int, SystemActivity] = {}
    for row in payload:
        try:
            activity[int(row["system_id"])] = SystemActivity(
                ship_kills=int(row.get("ship_kills", 0)),
                pod_kills=int(row.get("pod_kills", 0)),
                npc_kills=int(row.get("npc_kills", 0)),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return activity


async def fetch_system_kills() -> dict[int, SystemActivity] | None:
    """Returns None on any failure — the Bureau does not speculate offline."""
    try:
        async with httpx.AsyncClient(
            timeout=10.0, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = await client.get(ESI_SYSTEM_KILLS)
            response.raise_for_status()
            return parse_system_kills(response.json())
    except Exception:
        return None
