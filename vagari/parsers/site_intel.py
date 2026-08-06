"""Site intelligence — what a scanned name actually means.

Ported from PANTOSCOPE's probeScan.ts (canonical copy in the retrospex
repo; the AUGUR desktop app vendors the same file) — the ARCHAEOLOGY
circular's filing rules plus the INHALATION circular's gas tables. Keep
changes flowing back upstream.

No prices here: appraisal is a market activity and the Bureau is not a
market participant.
"""

from __future__ import annotations

from dataclasses import dataclass

from vagari.model.chain import SigGroup


@dataclass(frozen=True)
class GasCloud:
    gas: str        # "Fullerite-C540"
    type_id: int
    units: int


def _clouds(big: tuple[str, int], small: tuple[str, int],
            big_units: int, small_units: int) -> tuple[GasCloud, ...]:
    return (
        GasCloud(gas=f"Fullerite-{big[0]}", type_id=big[1], units=big_units),
        GasCloud(gas=f"Fullerite-{small[0]}", type_id=small[1], units=small_units),
    )


_F = {
    "C28": ("C28", 30375), "C32": ("C32", 30376), "C50": ("C50", 30370),
    "C60": ("C60", 30371), "C70": ("C70", 30372), "C72": ("C72", 30373),
    "C84": ("C84", 30374), "C320": ("C320", 30377), "C540": ("C540", 30378),
}

# Wormhole gas sites hold fixed clouds — the same two fullerenes at the same
# sizes every spawn — so contents are arithmetic, not folklore.
GAS_SITES: dict[str, tuple[GasCloud, ...]] = {
    "barren perimeter reservoir": _clouds(_F["C50"], _F["C60"], 12000, 6000),
    "token perimeter reservoir": _clouds(_F["C60"], _F["C70"], 12000, 6000),
    "minor perimeter reservoir": _clouds(_F["C70"], _F["C72"], 12000, 6000),
    "ordinary perimeter reservoir": _clouds(_F["C72"], _F["C84"], 12000, 6000),
    # The client spells it "Sizeable"; older records say "Sizable".
    "sizeable perimeter reservoir": _clouds(_F["C84"], _F["C50"], 12000, 6000),
    "sizable perimeter reservoir": _clouds(_F["C84"], _F["C50"], 12000, 6000),
    "bountiful frontier reservoir": _clouds(_F["C28"], _F["C32"], 20000, 4000),
    "vast frontier reservoir": _clouds(_F["C32"], _F["C28"], 20000, 4000),
    "instrumental core reservoir": _clouds(_F["C320"], _F["C540"], 24000, 2000),
    "vital core reservoir": _clouds(_F["C540"], _F["C320"], 24000, 2000),
}


def gas_contents(name: str) -> tuple[GasCloud, ...] | None:
    return GAS_SITES.get(name.strip().lower())


@dataclass(frozen=True)
class SiteVerdict:
    label: str           # "TIMED", "CACHE", "GAS", "NO NPCS", ...
    note: str            # one filing line
    hazard: bool         # rendered hot when True
    worth: str | None = None


_RELIC_TIERS = {
    "crumbling": "high-security grade, the easiest hacks",
    "decayed": "low-security grade",
    "ruined": "null or J-space grade, the best containers",
}
_DATA_TIERS = {
    "local": "high-security grade, the easiest hacks",
    "regional": "low-security grade",
    "central": "null or J-space grade, the best containers",
}
_SLEEPER_TIERS = {
    "perimeter": {"relic": "C1–C2", "data": "C1–C2"},
    "frontier": {"relic": "C3–C4", "data": "C3–C5"},
    "core": {"relic": "C5–C6", "data": "C6"},
}
_FACTIONS = ("sansha", "guristas", "blood raider", "serpentis", "angel")


def _classify_by_name(n: str) -> SiteVerdict | None:
    if "covert research facility" in n:
        return SiteVerdict(
            label="TIMED",
            note="Ghost site — the clock starts at warp entry and shows only "
                 "its final thirty seconds; one failed hack detonates the can.",
            hazard=True,
            worth="Covert Research Tools, Villard Wheels, Ascendancy "
                  "blueprints; variance is the point",
        )
    if "sleeper cache" in n:
        return SiteVerdict(
            label="CACHE",
            note="Sleeper Cache — both analysers required; environmental "
                 "punishments, rewards to match.",
            hazard=True,
            worth="several hundred million on a full clearing"
                  if "superior" in n
                  else "among the deepest containers in known space",
        )
    if "observatory infiltration" in n:
        return SiteVerdict(
            label="TRAPPED",
            note="Relic work among armed traps; one failed hack triggers the lockdown.",
            hazard=True,
        )
    if "aegis" in n:
        return SiteVerdict(
            label="ALARMED",
            note="The key hack summons its response fleet on success. Hack it aligned.",
            hazard=True,
        )
    if n.startswith("forgotten") or n.startswith("unsecured"):
        fam = "relic" if n.startswith("forgotten") else "data"
        tier = next((w for w in _SLEEPER_TIERS if w in n), None)
        grade = f" — {_SLEEPER_TIERS[tier][fam]} grade" if tier else ""
        return SiteVerdict(
            label="GUARDED",
            note=f"Sleeper {fam} site{grade}: defenders present, wave triggers "
                 "armed. Fit for the site, not the hack.",
            hazard=True,
            worth="yield scales with class; the escort is the price of admission",
        )
    if "reservoir" in n:
        tier = (
            "Core tier — C5, C6, and shattered systems; the best clouds on record"
            if "core" in n
            else "Frontier tier — the middle of the ladder"
            if "frontier" in n
            else "Perimeter tier — every class spawns them"
        )
        return SiteVerdict(
            label="GAS",
            note=f"{tier}. Empty at warp-in; Sleepers arrive after roughly "
                 "fifteen to twenty minutes on grid.",
            hazard=False,
            worth="the richest clouds in the game" if "core" in n
                  else "the middle shelf" if "frontier" in n
                  else "the low shelf",
        )
    if "nebula" in n:
        return SiteVerdict(
            label="GAS",
            note="A known-space nebula: booster gas country. The locals may "
                 "hold opinions about it.",
            hazard=False,
        )
    faction = next((f for f in _FACTIONS if f in n), None)
    if faction is not None:
        relic_tier = next((w for w in _RELIC_TIERS if n.startswith(w)), None)
        data_tier = next((w for w in _DATA_TIERS if n.startswith(w)), None)
        grade = (
            f" — {_RELIC_TIERS[relic_tier]}" if relic_tier
            else f" — {_DATA_TIERS[data_tier]}" if data_tier
            else ""
        )
        if relic_tier:
            worth = (
                "the top of the unguarded ladder" if relic_tier == "ruined"
                else "middling salvage yield" if relic_tier == "decayed"
                else "modest salvage yield"
            )
            if "sansha" in n:
                worth += "; Sansha space carries the strongest average relic loot"
        elif data_tier:
            worth = "lower average than relic work, with the blueprint lottery attached"
        else:
            worth = None
        return SiteVerdict(
            label="NO NPCS",
            note=f"Unguarded pirate site: containers only{grade}. The "
                 "neighbourhood is another matter.",
            hazard=False,
            worth=worth,
        )
    return None


def classify_site(group: SigGroup, name: str) -> SiteVerdict | None:
    """Filing verdict for a scanned site, or None when there is nothing to say.

    Combat and ore filings keep their category whatever pirate name they wear
    — "Guristas Hideaway" is a gunfight, not a container. Wormholes are
    connections, not sites; the chain itself is their verdict.
    """
    if group in (SigGroup.COMBAT, SigGroup.ORE, SigGroup.WORMHOLE):
        return None
    n = name.strip().lower()
    if not n:
        return None
    return _classify_by_name(n)
