"""Session: the engine-facing layer the UI drives.

Owns the live Chain, the Store, the view mode, and the command grammar.
Pure Python — fully testable without Textual.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from vagari.model.chain import Chain, ChainError, MassState, Signature, SigGroup
from vagari.model.reconcile import ReconcileReport, apply_despawn, reconcile
from vagari.model.store import Store
from vagari.parsers.catalog import lookup_system, lookup_wh_type
from vagari.parsers.scanner import parse_scan

_JCODE = re.compile(r"^[Jj]?\d{6}$")
_PREFIX = re.compile(r"^[A-Za-z]{3}(-\d{3})?$")

VIEWS = ("full", "paths", "gas")


@dataclass
class Session:
    store: Store
    chain: Chain
    view: str = "full"
    lazy_armed: bool = False
    last_report: ReconcileReport | None = None
    dirty: bool = field(default=False, init=False)  # set when chain changed (UI refresh)
    # ESI system-kill enrichment: system_id → SystemActivity; None until fetched.
    activity: dict = field(default_factory=dict, init=False)
    activity_fetched: bool = field(default=False, init=False)
    # Auto-recon samples per system_id: PvP kills at each fetch, capped.
    activity_history: dict = field(default_factory=dict, init=False)
    # K-space exit enrichment: system name → KSpaceInfo (session cache).
    kspace: dict = field(default_factory=dict, init=False)
    # zKill per-system stats: system_id → SystemKillStats (session cache).
    zkill_stats: dict = field(default_factory=dict, init=False)
    # Follow-me: an arrival the chain can't place — (system name, path we came from).
    pending_arrival: tuple[str, list[str]] | None = field(default=None, init=False)
    # Multibox follow-me: locked pilot (None = first to jump wins) and each
    # observed pilot's last known system.
    pilot_lock: str | None = field(default=None, init=False)
    known_pilots: dict = field(default_factory=dict, init=False)

    # -- lifecycle -----------------------------------------------------------

    @classmethod
    def open(cls, store: Store, name: str = "home") -> Session:
        chain = store.load_latest(name)
        if chain is None:
            chain = Chain(name=name)
            store.commit(chain)
        session = cls(store=store, chain=chain)
        session.pilot_lock = store.load_pilot()
        return session

    def _set_pilot_lock(self, pilot: str | None) -> None:
        self.pilot_lock = pilot
        self.store.save_pilot(pilot)

    def _commit(self, amend: bool = False) -> None:
        # amend=True for location-only changes: persisted, but not a new
        # undo step — a long roam should not flush the mapping history.
        (self.store.amend if amend else self.store.commit)(self.chain)
        self.dirty = True

    # -- paste ingestion -----------------------------------------------------

    def ingest(self, text: str) -> str:
        lines = parse_scan(text)
        if not lines:
            return "Nothing legible in that deposit. The Bureau is merely noting."
        lazy = self.lazy_armed
        self.lazy_armed = False
        report = reconcile(self.chain.current(), lines, lazy=lazy)
        self.last_report = report
        self._commit()
        parts = []
        if report.new:
            parts.append(f"NEW: {' '.join(report.new)}")
        if report.updated:
            parts.append(f"UPDATED: {' '.join(report.updated)}")
        if report.despawned:
            parts.append(f"DESPAWNED: {' '.join(report.despawned)} — `sweep` to strike")
        if report.blocked:
            parts.append(f"RETAINED (mapped children): {' '.join(report.blocked)}")
        return "; ".join(parts) if parts else "No changes. Chain of custody intact."

    # -- command grammar -----------------------------------------------------

    def execute(self, text: str) -> str:
        tokens = text.strip().split()
        if not tokens:
            return ""
        head, rest = tokens[0].lower(), tokens[1:]
        try:
            return self._dispatch(head, rest, text.strip())
        except ChainError as err:
            return f"REFUSED: {err}"

    def _dispatch(self, head: str, rest: list[str], raw: str) -> str:
        if head == "undo":
            return self.undo()
        if head == "redo":
            return self.redo()
        if head in ("top", "home"):
            self.chain.top()
            self._commit(amend=True)
            return f"Relocated to {self.chain.current().name}."
        if head == "up":
            self.chain.up()
            self._commit(amend=True)
            return f"Relocated to {self.chain.current().name}."
        if head == "nav" and rest:
            for prefix in rest:
                self.chain.nav(prefix)
            self._commit(amend=True)
            return f"Relocated to {self.chain.current().name}."
        if head in VIEWS:
            self.view = head
            self.dirty = True
            return f"View: {head}."
        if head == "lazy":
            self.lazy_armed = True
            return "LAZY ARMED: next deposit reconciles against the full sig list."
        if head == "add":
            return "Deposits are implicit: paste scan telemetry directly."
        if head == "sweep":
            return self._sweep(force="!" in rest or "force" in rest)
        if head == "flag" and rest:
            for prefix in rest:
                self.chain.flag_sig(prefix)
            self._commit()
            return f"Flagged: {' '.join(p.upper()[:3] for p in rest)}."
        if head in ("del", "del!") and rest:
            removed = []
            for prefix in rest:
                self.chain.delete_sig(prefix, force=head == "del!")
                removed.append(prefix.upper()[:3])
            self._commit()
            return f"Struck from record: {' '.join(removed)}."
        if head == "eol" and rest:
            return self._eol(rest[0])
        if head == "crit" and rest:
            return self._mass(rest[0])
        if head == "chain" and rest:
            return self._switch_chain(rest[0])
        if head == "pilot":
            return self.pilot_command(" ".join(rest) if rest else None)
        if head == "here" and rest:
            return self._name_system(self.chain.current(), rest[0].upper()
                                     if _JCODE.match(rest[0]) else " ".join(rest))
        if head == "k162":
            return self.file_k162()
        if head == "rekey" and len(rest) == 2:
            return self._rekey(rest[0], rest[1])
        if len(rest) == 2 and rest[0] == "=" and _PREFIX.match(head):
            return self._rekey(head, rest[1])
        if head in ("cull", "cull!"):
            return self._cull(force=head == "cull!")
        if _PREFIX.match(head) and rest:
            return self._sig_command(head, rest)
        return f"Unrecognised submission: {raw!r}. See `?` for accepted forms."

    # -- helpers -------------------------------------------------------------

    def _sweep(self, force: bool = False) -> str:
        if not self.last_report or not (
            self.last_report.despawned or (force and self.last_report.blocked)
        ):
            return "Nothing pending a sweep."
        targets = list(self.last_report.despawned)
        if force:
            targets += self.last_report.blocked
        removed = apply_despawn(self.chain.current(), targets, force=force)
        self.last_report = None
        self._commit()
        return f"Struck from record: {' '.join(removed)}." if removed else "Nothing swept."

    def _eol(self, prefix: str) -> str:
        conn = self.chain.current().find_connection(prefix)
        if conn is None:
            raise ChainError(f"{prefix.upper()[:3]} is not an opened wormhole")
        conn.eol = not conn.eol
        self._commit()
        state = "END OF LIFE" if conn.eol else "no longer EOL"
        return f"{conn.sig_prefix} marked {state}."

    def _mass(self, prefix: str) -> str:
        conn = self.chain.current().find_connection(prefix)
        if conn is None:
            raise ChainError(f"{prefix.upper()[:3]} is not an opened wormhole")
        cycle = [MassState.FRESH, MassState.REDUCED, MassState.CRITICAL]
        conn.mass = cycle[(cycle.index(conn.mass) + 1) % 3]
        self._commit()
        return f"{conn.sig_prefix} mass: {conn.mass.value.upper()}."

    def _switch_chain(self, name: str) -> str:
        self.chain = self.store.load_latest(name) or Chain(name=name)
        self.store.commit(self.chain)
        self.view = "full"
        self.last_report = None
        self.dirty = True
        return f"Chain of custody: {name}."

    def _sig_command(self, prefix: str, rest: list[str]) -> str:
        arg = rest[0]
        if _JCODE.match(arg):
            return self._open_jcode(prefix, arg)
        wh_type = lookup_wh_type(arg)
        if wh_type is not None and len(rest) == 1:
            return self._set_wh_type(prefix, wh_type.code)
        label = " ".join(rest)
        sig = self.chain.label_sig(prefix, label)
        self._commit()
        return f"{sig.prefix} labelled {label!r}."

    def _open_jcode(self, prefix: str, jcode: str) -> str:
        info = lookup_system(jcode)
        here = self.chain.current()
        if here.find_connection(prefix) is not None:
            raise ChainError(f"{prefix.upper()[:3]} is already opened")
        if info is not None:
            conn = self.chain.open_connection(
                prefix, info.jcode, jclass=info.jclass,
                statics=info.static_display, effect=info.effect,
            )
            self._commit()
            eff = f" · {info.effect}" if info.effect else ""
            return f"{conn.sig_prefix} → {info.jcode} [{info.jclass}+{info.static_display}{eff}]."
        name = jcode.upper() if jcode.upper().startswith("J") else f"J{jcode}"
        conn = self.chain.open_connection(prefix, name)
        self._commit()
        return f"{conn.sig_prefix} → {name} [not in Bureau records]."

    def _set_wh_type(self, prefix: str, code: str) -> str:
        wh_type = lookup_wh_type(code)
        here = self.chain.current()
        conn = here.find_connection(prefix)
        if conn is None:
            conn = self.chain.open_connection(prefix, "?", jclass=wh_type.target_display
                                              if wh_type.target_class else None,
                                              wh_type=code)
        else:
            conn.wh_type = code
        self._commit()
        life = f", {wh_type.lifetime_hours:g}h" if wh_type.lifetime_hours else ""
        return f"{conn.sig_prefix} typed {code} (→{wh_type.target_display}{life})."

    # -- follow-me (chatlog) -------------------------------------------------

    def follow_event(self, pilot: str, system: str, initial: bool) -> str | None:
        """Multibox policy for tailer events.

        Follow only the locked pilot. With no lock, the first pilot who
        actually JUMPS (a live event) takes the lock — the character moving
        through space is the one being flown. Initial events only record
        each pilot's position so `pilot <name>` can sync immediately.
        """
        self.known_pilots[pilot] = system
        if initial:
            if self.pilot_lock == pilot:
                return self.follow(system)
            return None
        if self.pilot_lock is None:
            self._set_pilot_lock(pilot)
            moved = self.follow(system)
            return f"FOLLOWING {pilot}. " + (moved or "Position noted.")
        if pilot != self.pilot_lock:
            return None
        return self.follow(system)

    def pilot_command(self, arg: str | None) -> str:
        """`pilot` — report; `pilot off` — unlock; `pilot <name>` — lock."""
        if not arg:
            roster = ", ".join(
                f"{p} ({s})" + (" ←" if p == self.pilot_lock else "")
                for p, s in sorted(self.known_pilots.items())
            ) or "none observed yet"
            lock = self.pilot_lock or "first pilot to jump"
            return f"Following: {lock}. On record: {roster}."
        if arg.lower() == "off":
            self._set_pilot_lock(None)
            return "Lock released — following the first pilot to jump."
        match = next(
            (p for p in self.known_pilots if p.lower() == arg.lower()), None
        )
        pilot = match or arg
        self._set_pilot_lock(pilot)
        known = self.known_pilots.get(pilot)
        if known:
            moved = self.follow(known)
            return f"FOLLOWING {pilot}. " + (moved or f"Position: {known}.")
        return f"FOLLOWING {pilot} — no position on record yet."

    def follow(self, name: str) -> str | None:
        """The pilot entered `name` in-game; move ◉ YOU. None = no change."""
        chain = self.chain
        current = chain.current()
        if current.name == name:
            self.pending_arrival = None  # back somewhere accounted for
            return None

        # Fresh chain: first observed system names the root.
        if chain.root.name == "HOME" and not chain.root.connections:
            return self._name_system(chain.root, name)

        for conn in current.connections:
            if conn.child.name == name:
                chain.location.append(conn.sig_prefix)
                self.pending_arrival = None
                self._commit(amend=True)
                return f"Followed you through {conn.sig_prefix} to {name}."

        if chain.location:
            parent = chain.system_at(chain.location[:-1])
            if parent.name == name:
                chain.location.pop()
                self.pending_arrival = None
                self._commit(amend=True)
                return f"Followed you back up to {name}."

        found = self._find_system(name)
        if found is not None:
            chain.location = found
            self.pending_arrival = None
            self._commit(amend=True)
            return f"Relocated ◉ YOU to {name} (elsewhere in the chain)."

        self.pending_arrival = (name, list(chain.location))
        return (
            f"Arrived in UNMAPPED {name}. Press k (or submit `k162`) to file it "
            f"as a K162 out of {current.name}."
        )

    def file_k162(self) -> str:
        """File a pending unmapped arrival as a K162 child of where we came from."""
        if self.pending_arrival is None:
            return "No unmapped arrival pending. The record is at peace."
        name, from_path = self.pending_arrival
        origin = self.chain.system_at(from_path)
        prefix = self._placeholder_prefix(origin)
        origin.sigs.append(
            Signature(sig_id=f"{prefix}-000", group=SigGroup.WORMHOLE,
                      label="K162 (unscanned)")
        )
        info = lookup_system(name)
        saved_location = self.chain.location
        self.chain.location = list(from_path)
        try:
            self.chain.open_connection(
                prefix, info.jcode if info else name,
                jclass=info.jclass if info else None,
                statics=info.static_display if info else None,
                effect=info.effect if info else None,
                wh_type="K162",
            )
        except ChainError:
            self.chain.location = saved_location
            raise
        self.chain.location = list(from_path) + [prefix]
        self.pending_arrival = None
        self._commit()
        return (
            f"Filed {name} as K162 via placeholder {prefix} — relabel it when "
            "you scan the real signature."
        )

    def find_matches(self, query: str) -> list[tuple]:
        """Tree-node data tuples matching a query: system names first,
        then signatures by prefix, site name, or label."""
        q = query.strip().lower()
        if not q:
            return []
        matches: list[tuple] = []
        queue: list[tuple[list[str], object]] = [([], self.chain.root)]
        while queue:
            path, system = queue.pop(0)
            if q in system.name.lower():
                matches.append(("system", path))
            for sig in system.sigs:
                haystack = f"{sig.prefix} {sig.name} {sig.label}".lower()
                if q in haystack:
                    matches.append(("sig", path, sig.prefix))
            for conn in system.connections:
                queue.append((path + [conn.sig_prefix], conn.child))
        return matches

    def unresolved_kspace_names(self) -> list[str]:
        """Chain system names that are neither catalogued J-space nor
        already resolved — candidates for ESI k-space lookup."""
        names: list[str] = []
        queue = [self.chain.root]
        while queue:
            system = queue.pop(0)
            name = system.name
            if (
                name not in ("HOME", "?")
                and name not in self.kspace
                and lookup_system(name) is None
                and name not in names
            ):
                names.append(name)
            queue.extend(conn.child for conn in system.connections)
        return names

    def _find_system(self, name: str) -> list[str] | None:
        """Breadth-first search for a system by name; returns its path."""
        queue: list[tuple[list[str], object]] = [([], self.chain.root)]
        while queue:
            path, system = queue.pop(0)
            if system.name == name:
                return path
            for conn in system.connections:
                queue.append((path + [conn.sig_prefix], conn.child))
        return None

    @staticmethod
    def _placeholder_prefix(system) -> str:
        from itertools import product
        from string import ascii_uppercase

        for combo in product("Z", ascii_uppercase, ascii_uppercase):
            prefix = "".join(combo)
            if system.find_sig(prefix) is None:
                return prefix
        raise ChainError("no placeholder prefixes left; the Bureau is impressed")

    def _rekey(self, old: str, new: str) -> str:
        """Refile a signature under its real prefix — for K162 placeholders
        whose true signature has since been scanned. Preserves the connection
        and everything mapped behind it."""
        if not _PREFIX.match(new):
            raise ChainError(f"{new!r} is not a signature prefix")
        here = self.chain.current()
        sig = here.find_sig(old)
        if sig is None:
            raise ChainError(f"no signature {old.upper()[:3]!r} in {here.name}")
        new_prefix = new.upper()[:3]
        if here.find_sig(new_prefix) is not None:
            raise ChainError(f"{new_prefix} already exists here")
        old_prefix = sig.prefix
        sig.sig_id = f"{new_prefix}-000"
        if sig.label == "K162 (unscanned)":
            sig.label = ""
        conn = here.find_connection(old_prefix)
        if conn is not None:
            conn.sig_prefix = new_prefix
        self._commit()
        return f"{old_prefix} refiled as {new_prefix}. The record forgives."

    def _cull(self, force: bool = False) -> str:
        """Strike connections past their book lifetime (EXPIRED in the tree)."""
        from vagari.model.lifetime import LifeStatus, assess

        here = self.chain.current()
        expired = [
            c.sig_prefix for c in list(here.connections)
            if assess(c).status is LifeStatus.EXPIRED
        ]
        if not expired:
            return "Nothing past its book lifetime here."
        removed, blocked = [], []
        for prefix in expired:
            try:
                here.remove_sig(prefix, force=force)
                removed.append(prefix)
            except ChainError:
                blocked.append(prefix)
        if removed:
            self._commit()
        parts = []
        if removed:
            parts.append(f"Culled: {' '.join(removed)}.")
        if blocked:
            parts.append(
                f"Retained (mapped children): {' '.join(blocked)} — `cull!` to force."
            )
        return " ".join(parts)

    # -- activity history (auto-recon sampling) ------------------------------

    def sample_activity(self, cap: int = 24) -> None:
        """Record a per-system PvP-kill sample for every system in the chain."""
        systems: list = []

        def walk(system) -> None:
            systems.append(system)
            for conn in system.connections:
                walk(conn.child)

        walk(self.chain.root)
        for system in systems:
            info = lookup_system(system.name)
            if info is None:
                continue
            act = self.activity.get(info.system_id)
            pvp = (act.ship_kills + act.pod_kills) if act else 0
            history = self.activity_history.setdefault(info.system_id, [])
            history.append(pvp)
            del history[:-cap]

    def _name_system(self, system, name: str) -> str:
        system.name = name
        info = lookup_system(name)
        if info is not None:
            system.jclass = info.jclass
            system.statics = info.static_display
            system.effect = info.effect
        self._commit()
        return f"This system is now on record as {name}."

    def jump(self, path: list[str]) -> str:
        """Set the current location to an already-mapped path (tree navigation)."""
        self.chain.system_at(path)  # validates
        self.chain.location = list(path)
        self._commit(amend=True)
        return f"Relocated to {self.chain.current().name}."

    # -- undo / redo ---------------------------------------------------------

    def undo(self) -> str:
        chain = self.store.undo(self.chain.name)
        if chain is None:
            return "Nothing to undo. The record stands."
        self.chain = chain
        self.dirty = True
        return "Reverted one revision."

    def redo(self) -> str:
        chain = self.store.redo(self.chain.name)
        if chain is None:
            return "Nothing to redo."
        self.chain = chain
        self.dirty = True
        return "Reinstated one revision."

    # -- display helpers (UI-agnostic) ---------------------------------------

    def breadcrumb(self) -> str:
        names = [self.chain.root.name]
        system = self.chain.root
        for prefix in self.chain.location:
            system = system.find_connection(prefix).child
            names.append(system.name)
        return " ▸ ".join(names)
