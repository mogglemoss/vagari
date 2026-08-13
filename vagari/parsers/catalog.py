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
    source_classes: tuple[str, ...]   # raw keys that can spawn it, e.g. ("c3",)
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
    class_key: str              # raw key: "c1".."c13", "thera", drifter names
    effect: str | None
    shattered: bool
    statics: tuple[str, ...]    # wormhole-type codes, e.g. ("Z060",)
    static_display: str         # e.g. "N" or "C3,H"
    region: str | None


def _data(name: str) -> object:
    text = (resources.files("vagari") / "data" / name).read_text(encoding="utf-8")
    return json.loads(text)


@lru_cache(maxsize=1)
def load_wormhole_types() -> dict[str, WormholeType]:
    types: dict[str, WormholeType] = {}
    for t in _data("wormhole_types.json"):
        types[t["code"]] = WormholeType(
            code=t["code"],
            target_class=t["targetClass"],
            is_static=t["isStatic"],
            source_classes=tuple(t.get("sourceClasses") or []),
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
            class_key=s["classKey"],
            effect=s["effect"],
            shattered=s["shattered"],
            statics=statics,
            static_display=",".join(targets),
            region=s.get("region"),
        )
    return systems


_kspace_cache: dict | None = None


def kspace_names() -> list[str]:
    """Every charted k-space system name, proper-cased, sorted."""
    global _kspace_cache
    if _kspace_cache is None:
        _kspace_cache = _data("kspace.json")
    return sorted(v[0] for v in _kspace_cache.values())


def lookup_kspace(name: str):
    """K-space system by name, case-insensitive — (proper name, system id,
    true sec, region) from the bundled SDE extract, or None."""
    global _kspace_cache
    if _kspace_cache is None:
        _kspace_cache = _data("kspace.json")
    hit = _kspace_cache.get(name.strip().lower())
    return tuple(hit) if hit else None


def lookup_system(key: str) -> SystemInfo | None:
    """Look up by 'J105443', 'j105443', or bare '105443'."""
    key = key.strip().upper()
    if key and not key.startswith("J") and key.isdigit():
        key = "J" + key
    return load_systems().get(key)


def lookup_wh_type(code: str) -> WormholeType | None:
    return load_wormhole_types().get(code.strip().upper())


@lru_cache(maxsize=1)
def _effect_tables() -> dict[str, dict[str, list[str]]]:
    return _data("effects.json")


@lru_cache(maxsize=1)
def _effect_power() -> dict[str, int]:
    """classKey → effect power 1–6 (C13 hits like C6, drifter systems like C2)."""
    return {
        c["key"]: c["effectPower"]
        for c in _data("classes.json")
        if c.get("effectPower")
    }


def effect_details(effect: str, class_key: str) -> list[tuple[str, str]] | None:
    """[(attribute, value-at-this-class)] for a weather effect, or None."""
    table = _effect_tables().get(effect)
    power = _effect_power().get(class_key)
    if table is None or power is None:
        return None
    index = power - 1
    return [
        (attr, values[index])
        for attr, values in table.items()
        if index < len(values)
    ]


def candidate_types(jcode: str) -> list[WormholeType]:
    """The short list that covers most holes: K162 (someone's entrance —
    true half the time) plus this system's statics. Wanderers exist but a
    long list buries the likely answers; type rare codes by hand."""
    info = lookup_system(jcode)
    if info is None:
        return []
    types = load_wormhole_types()
    out = [types["K162"]] if "K162" in types else []
    out += [types[code] for code in info.statics if code in types]
    return out
