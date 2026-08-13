"""The chain data model: Chain → System → Signature / Connection.

Everything is timestamped; everything serialises to plain dicts for the
snapshot store. No I/O in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChainError(Exception):
    """A chain operation that cannot be honoured (unknown sig, guarded delete...)."""


class SigGroup(str, Enum):
    WORMHOLE = "Wormhole"
    COMBAT = "Combat Site"
    DATA = "Data Site"
    RELIC = "Relic Site"
    GAS = "Gas Site"
    ORE = "Ore Site"
    UNKNOWN = "Unknown"


class MassState(str, Enum):
    FRESH = "fresh"
    REDUCED = "reduced"
    CRITICAL = "critical"


def norm_prefix(text: str) -> str:
    """'abc-123' / 'abc' → 'ABC'."""
    return text.strip()[:3].upper()


@dataclass
class Signature:
    sig_id: str                     # "ABC-123" as pasted, or bare "ABC"
    group: SigGroup = SigGroup.UNKNOWN
    name: str = ""                  # site name once fully scanned
    signal: float = 0.0             # scan strength 0–100
    label: str = ""                 # user label, never overwritten by pastes
    flagged: bool = False
    first_seen: datetime = field(default_factory=utcnow)
    last_seen: datetime = field(default_factory=utcnow)

    @property
    def prefix(self) -> str:
        return norm_prefix(self.sig_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sig_id": self.sig_id,
            "group": self.group.value,
            "name": self.name,
            "signal": self.signal,
            "label": self.label,
            "flagged": self.flagged,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Signature:
        return cls(
            sig_id=d["sig_id"],
            group=SigGroup(d["group"]),
            name=d["name"],
            signal=d["signal"],
            label=d["label"],
            flagged=d["flagged"],
            first_seen=datetime.fromisoformat(d["first_seen"]),
            last_seen=datetime.fromisoformat(d["last_seen"]),
        )


@dataclass
class Connection:
    """An opened wormhole: a signature in the parent that leads to a child system."""

    sig_prefix: str
    child: System
    # The hole's TRUE type ("H296", "U210", …) whichever side it was read
    # from. K162 is not a type but an end: `k162_end` records which end
    # wears it — "parent" (someone opened into the parent; entering it is
    # forward travel), "child" (the parent side was opened first), or None
    # (not yet established).
    wh_type: str | None = None
    k162_end: str | None = None
    # When the pilot marked end-of-life — EVE's ~4h clock runs from here.
    eol_marked_at: datetime | None = None
    # The far side's sig prefix in the CHILD system. Pairs the two halves
    # of one wormhole; direction-neutral.
    return_prefix: str | None = None
    eol: bool = False
    mass: MassState = MassState.FRESH
    opened_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sig_prefix": self.sig_prefix,
            "child": self.child.to_dict(),
            "wh_type": self.wh_type,
            "k162_end": self.k162_end,
            "eol_marked_at": (
                self.eol_marked_at.isoformat() if self.eol_marked_at else None
            ),
            "return_prefix": self.return_prefix,
            "eol": self.eol,
            "mass": self.mass.value,
            "opened_at": self.opened_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Connection:
        return cls(
            sig_prefix=d["sig_prefix"],
            child=System.from_dict(d["child"]),
            # Legacy records used wh_type="K162" to mean "the parent-side
            # sig is a K162"; the true type was unknown.
            wh_type=None if d["wh_type"] == "K162" else d["wh_type"],
            k162_end=d.get(
                "k162_end", "parent" if d["wh_type"] == "K162" else None
            ),
            eol_marked_at=(
                datetime.fromisoformat(d["eol_marked_at"])
                if d.get("eol_marked_at")
                else None
            ),
            return_prefix=d.get("return_prefix"),
            eol=d["eol"],
            mass=MassState(d["mass"]),
            opened_at=datetime.fromisoformat(d["opened_at"]),
        )


@dataclass
class System:
    name: str                       # "J105443", k-space name, or user alias
    jclass: str | None = None       # "C2"
    statics: str | None = None      # "3,H"
    effect: str | None = None       # "Magnetar"
    sigs: list[Signature] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)
    # Set while this system is an adrift fragment root (severed or filed
    # disconnected); cleared on adoption.
    adrift_since: datetime | None = None

    def find_sig(self, prefix: str) -> Signature | None:
        p = norm_prefix(prefix)
        for sig in self.sigs:
            if sig.prefix == p:
                return sig
        return None

    def find_connection(self, prefix: str) -> Connection | None:
        p = norm_prefix(prefix)
        for conn in self.connections:
            if conn.sig_prefix == p:
                return conn
        return None

    def remove_sig(self, prefix: str, force: bool = False) -> Signature:
        """Remove a signature (and its connection, if any).

        Refuses to remove a sig whose connection still has mapped content
        beneath it, unless forced.
        """
        sig = self.find_sig(prefix)
        if sig is None:
            raise ChainError(f"no signature {norm_prefix(prefix)!r} here")
        conn = self.find_connection(prefix)
        if conn is not None:
            child = conn.child
            if (child.sigs or child.connections) and not force:
                raise ChainError(
                    f"{sig.prefix} leads to {child.name} which still has mapped "
                    "content; force to remove the whole branch"
                )
            self.connections.remove(conn)
        self.sigs.remove(sig)
        return sig

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "jclass": self.jclass,
            "statics": self.statics,
            "effect": self.effect,
            "sigs": [s.to_dict() for s in self.sigs],
            "connections": [c.to_dict() for c in self.connections],
            "adrift_since": (
                self.adrift_since.isoformat() if self.adrift_since else None
            ),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> System:
        return cls(
            name=d["name"],
            jclass=d["jclass"],
            statics=d["statics"],
            effect=d["effect"],
            sigs=[Signature.from_dict(s) for s in d["sigs"]],
            connections=[Connection.from_dict(c) for c in d["connections"]],
            adrift_since=(
                datetime.fromisoformat(d["adrift_since"])
                if d.get("adrift_since")
                else None
            ),
        )


@dataclass
class Chain:
    """A forest of mapped fragments. Paths are [fragment_index, *sig_prefixes];
    the location's first element names the fragment ◉ YOU is in."""

    name: str = "home"
    roots: list[System] = field(default_factory=lambda: [System(name="HOME")])
    location: list = field(default_factory=lambda: [0])
    home: str | None = None  # a system NAME; None = this fragment's root

    @property
    def root(self) -> System:
        """The first fragment — the traditional single-tree view."""
        return self.roots[0]

    # -- navigation ----------------------------------------------------------

    def system_at(self, path: list) -> System:
        if not path or not isinstance(path[0], int):
            raise ChainError(f"malformed path {path!r} (no fragment index)")
        try:
            system = self.roots[path[0]]
        except IndexError:
            raise ChainError(f"no fragment #{path[0]} on this chain") from None
        for prefix in path[1:]:
            conn = system.find_connection(prefix)
            if conn is None:
                raise ChainError(
                    f"no opened wormhole {norm_prefix(prefix)!r} in {system.name}"
                )
            system = conn.child
        return system

    def current(self) -> System:
        return self.system_at(self.location)

    def nav(self, *prefixes: str) -> System:
        path = list(self.location)
        for prefix in prefixes:
            self.system_at(path + [prefix])  # validates
            path.append(norm_prefix(prefix))
        self.location = path
        return self.current()

    def up(self) -> System:
        if len(self.location) > 1:
            self.location.pop()
        return self.current()

    def top(self) -> System:
        """To the root of the CURRENT fragment."""
        self.location = [self.location[0]]
        return self.current()

    # -- sig operations (all act on the current system) ----------------------

    def _require_sig(self, prefix: str) -> Signature:
        sig = self.current().find_sig(prefix)
        if sig is None:
            raise ChainError(f"no signature {norm_prefix(prefix)!r} in {self.current().name}")
        return sig

    def label_sig(self, prefix: str, label: str) -> Signature:
        sig = self._require_sig(prefix)
        sig.label = label
        return sig

    def flag_sig(self, prefix: str, flagged: bool = True) -> Signature:
        sig = self._require_sig(prefix)
        sig.flagged = flagged
        return sig

    def delete_sig(self, prefix: str, force: bool = False) -> Signature:
        return self.current().remove_sig(prefix, force=force)

    def open_connection(
        self,
        prefix: str,
        dest_name: str,
        *,
        jclass: str | None = None,
        statics: str | None = None,
        effect: str | None = None,
        wh_type: str | None = None,
    ) -> Connection:
        """Turn a signature into an opened wormhole leading to a new child system."""
        sig = self._require_sig(prefix)
        here = self.current()
        if here.find_connection(prefix) is not None:
            raise ChainError(f"{sig.prefix} is already opened")
        sig.group = SigGroup.WORMHOLE
        child = System(name=dest_name, jclass=jclass, statics=statics, effect=effect)
        conn = Connection(sig_prefix=sig.prefix, child=child, wh_type=wh_type)
        here.connections.append(conn)
        return conn

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "roots": [r.to_dict() for r in self.roots],
            "location": list(self.location),
            "home": self.home,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Chain:
        if "root" in d:  # legacy single-tree snapshot
            return cls(
                name=d["name"],
                roots=[System.from_dict(d["root"])],
                location=[0] + list(d["location"]),
            )
        return cls(
            name=d["name"],
            roots=[System.from_dict(r) for r in d["roots"]],
            location=list(d["location"]),
            home=d.get("home"),
        )
