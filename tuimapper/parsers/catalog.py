"""Loader for the bundled J-space reference data (see data/ATTRIBUTION.md).

Two datasets, both derived from anoik.is via the spookyspace ingest:

- ``systems.json`` — every J-space system: class, effect, statics (as
  wormhole-type codes), shattered flag, and more we don't surface yet
  (region, sun, planets).
- ``wormhole_types.json`` — every wormhole type: target class, total/jump
  mass, lifetime, size.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

_CLASS_DISPLAY = {
    "hs": "H",
    "ls": "L",
    "ns": "N",
}


def _display_class(key: str | None) -> str:
    """'c13' → 'C13', 'hs' → 'H', 'thera' → 'Thera'."""
    if not key:
        return "?"
    if key in _CLASS_DISPLAY:
        return _CLASS_DISPLAY[key]
    if key.startswith("c") and key[1:].isdigit():
        return key.upper()
    return key.capitalize()


@dataclass(frozen=True)
class WormholeType:
    code: str                   # "N110", "K162", ...
    target_class: str | None    # raw key: "c3", "hs", None (K162)
    is_static: bool
    total_mass: int
    jump_mass: int
    lifetime_hours: float
    mass_regen: int
    size: str

    @property
    def target_display(self) -> str:
        return _display_class(self.target_class)


@dataclass(frozen=True)
class SystemInfo:
    jcode: str                  # "J105443"
    system_id: int              # EVE system id (for ESI enrichment)
    jclass: str                 # display: "C1".."C13", "Thera", "Sentinel", ...
    effect: str | None
    shattered: bool
    statics: tuple[str, ...]    # wormhole-type codes, e.g. ("Z060",)
    static_display: str         # e.g. "N" or "C3,H"
    region: str | None


def _data(name: str) -> object:
    text = (resources.files("tuimapper") / "data" / name).read_text(encoding="utf-8")
    return json.loads(text)


@lru_cache(maxsize=1)
def load_wormhole_types() -> dict[str, WormholeType]:
    types: dict[str, WormholeType] = {}
    for t in _data("wormhole_types.json"):
        types[t["code"]] = WormholeType(
            code=t["code"],
            target_class=t["targetClass"],
            is_static=t["isStatic"],
            total_mass=t["totalMass"],
            jump_mass=t["jumpMass"],
            lifetime_hours=t["lifetimeHours"],
            mass_regen=t["massRegen"],
            size=t["size"],
        )
    return types


@lru_cache(maxsize=1)
def load_systems() -> dict[str, SystemInfo]:
    types = load_wormhole_types()
    systems: dict[str, SystemInfo] = {}
    for s in _data("systems.json"):
        statics = tuple(s["statics"])
        targets = [
            types[code].target_display if code in types else "?" for code in statics
        ]
        systems[s["name"].upper()] = SystemInfo(
            jcode=s["name"],
            system_id=s["systemId"],
            jclass=_display_class(s["classKey"]),
            effect=s["effect"],
            shattered=s["shattered"],
            statics=statics,
            static_display=",".join(targets),
            region=s.get("region"),
        )
    return systems


def lookup_system(key: str) -> SystemInfo | None:
    """Look up by 'J105443', 'j105443', or bare '105443'."""
    key = key.strip().upper()
    if key and not key.startswith("J") and key.isdigit():
        key = "J" + key
    return load_systems().get(key)


def lookup_wh_type(code: str) -> WormholeType | None:
    return load_wormhole_types().get(code.strip().upper())
