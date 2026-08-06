"""K-space exit enrichment — security status and region for named exits.

J-space systems come from the bundled catalogue; a chain's k-space exits
("Jita", "Amarr") are just names until resolved here via public ESI:
name → id → system (security, constellation) → region. Four requests per
system, cached for the session, fail-silent offline.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from vagari.enrichers.activity import USER_AGENT

ESI = "https://esi.evetech.net/latest"


@dataclass(frozen=True)
class KSpaceInfo:
    system_id: int
    security: float          # CCP true sec, e.g. 0.9459…
    region: str

    @property
    def sec_display(self) -> str:
        """CCP rounds displayed sec to one decimal."""
        return f"{round(self.security, 1):.1f}"

    @property
    def band(self) -> str:
        """'H' / 'L' / 'N' by the displayed (rounded) security."""
        rounded = round(self.security, 1)
        if rounded >= 0.5:
            return "H"
        if rounded > 0.0:
            return "L"
        return "N"


def pick_system_id(ids_payload: dict, name: str) -> int | None:
    """The /universe/ids/ response also matches corps and alliances —
    only the systems bucket counts."""
    for row in ids_payload.get("systems") or []:
        if row.get("name", "").lower() == name.lower():
            return row.get("id")
    return None


async def resolve_systems(names: list[str]) -> dict[str, KSpaceInfo]:
    """Resolve k-space system names. Unresolvable names are simply absent."""
    resolved: dict[str, KSpaceInfo] = {}
    if not names:
        return resolved
    try:
        async with httpx.AsyncClient(
            timeout=10.0, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = await client.post(f"{ESI}/universe/ids/", json=names)
            response.raise_for_status()
            payload = response.json()
            for name in names:
                system_id = pick_system_id(payload, name)
                if system_id is None:
                    continue
                system = (await client.get(f"{ESI}/universe/systems/{system_id}/")).json()
                constellation = (
                    await client.get(
                        f"{ESI}/universe/constellations/{system['constellation_id']}/"
                    )
                ).json()
                region = (
                    await client.get(
                        f"{ESI}/universe/regions/{constellation['region_id']}/"
                    )
                ).json()
                resolved[name] = KSpaceInfo(
                    system_id=system_id,
                    security=system["security_status"],
                    region=region["name"],
                )
    except Exception:
        return resolved  # whatever resolved before the failure still counts
    return resolved
