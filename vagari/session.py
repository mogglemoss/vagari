"""Session: the engine-facing layer the UI drives.

Owns the live Chain, the Store, the view mode, and the command grammar.
Pure Python — fully testable without Textual.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from vagari.model.chain import (
    Chain, ChainError, Connection, MassState, Signature, SigGroup, System,
    utcnow,
)
from vagari.model.reconcile import ReconcileReport, apply_despawn, reconcile
from vagari.model.store import Store
from vagari.parsers.catalog import lookup_system, lookup_wh_type
from vagari.parsers.scanner import parse_scan

_JCODE = re.compile(r"^[Jj]?\d{6}$")
_PREFIX = re.compile(r"^[A-Za-z]{3}(-\d{3})?$")

VIEWS = ("full", "paths", "sites", "gas", "combat")


@dataclass
class Session:
    store: Store
    chain: Chain
    view: str = "full"
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
    def open(cls, store: Store, name: str | None = None) -> Session:
        if name is None:
            name = store.load_active() or "home"
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

    def orientation_hint(self) -> str | None:
        """The first-session ladder: three hints, each earned by doing the
        previous thing, then silence forever. Veterans with existing chains
        graduate immediately."""
        stage = self.store.load_orientation()
        if stage >= 3:
            return None

        def any_sigs() -> bool:
            return any(r.sigs or r.connections for r in self.chain.roots)

        def any_conns() -> bool:
            def walk(sys) -> bool:
                return bool(sys.connections) or any(
                    walk(c.child) for c in sys.connections
                )
            return any(walk(r) for r in self.chain.roots)

        if stage == 0:
            if any_sigs():
                self.store.save_orientation(1)
                return self.orientation_hint()
            return (
                "FORM ACB-00 (ORIENTATION): deposit a probe scan — Ctrl+A, "
                "Ctrl+C in the scanner window, then paste here."
            )
        if stage == 1:
            if any_conns():
                self.store.save_orientation(2)
                return self.orientation_hint()
            return (
                "ORIENTATION 2/3: select a wormhole — its candidate types "
                "are in the dossier. Click one, or submit `abc H296`."
            )
        self.store.save_orientation(3)
        return (
            "ORIENTATION 3/3: jump it in game — the map follows you. "
            "`?` holds the full reference. The Bureau is done teaching."
        )

    # -- paste ingestion -----------------------------------------------------

    def ingest(self, text: str) -> str:
        lines = parse_scan(text)
        if not lines:
            return "Nothing legible in that deposit. The Bureau is merely noting."
        current = self.chain.current()
        first_scan = not current.sigs
        # Every deposit reports despawn candidates; `sweep` is the only
        # destructive step, so reporting costs nothing and forgets nothing.
        report = reconcile(current, lines, lazy=True)
        self.last_report = report
        return_note = ""
        if first_scan:
            return_note = self._pair_return_from_first_scan(current)
        self._commit()
        parts = []
        if return_note:
            parts.append(return_note)
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
        # An @System token anywhere addresses a signature in that system;
        # without it, sigs resolve current-system-first, then chain-wide.
        at = None
        for i, tok in enumerate(rest):
            if tok.startswith("@") and len(tok) > 1:
                at = tok[1:]
                rest = rest[:i] + rest[i + 1:]
                break
        if head == "undo":
            return self.undo()
        if head == "redo":
            return self.redo()
        if head == "top":
            self.chain.top()
            self._commit(amend=True)
            return f"Relocated to {self.chain.current().name}."
        if head in ("home", "route"):
            return self.homeward()
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
            return (
                "Deposits always report despawn candidates now; "
                "`sweep` strikes them."
            )
        if head == "add":
            return "Deposits are implicit: paste scan telemetry directly."
        if head == "sweep":
            return self._sweep(force="!" in rest or "force" in rest)
        if head == "flag" and rest:
            for prefix in rest:
                _, _, sig = self._locate(prefix, at)
                sig.flagged = True
            self._commit()
            return f"Flagged: {' '.join(p.upper()[:3] for p in rest)}."
        if head in ("strike", "strike!", "del", "del!") and rest:
            return self._strike(rest, at, force=head.endswith("!"),
                                sig_only=head.startswith("del"))
        if head == "eol" and rest:
            return self._eol(rest[0], at)
        if head == "crit" and rest:
            return self._mass(rest[0], at)
        if head == "return" and rest:
            return self._set_return(
                rest[0], at, rest[1] if len(rest) > 1 else None
            )
        if head == "return!":
            return self._unpair_return(at)
        if head == "chain" and rest:
            return self._switch_chain(rest[0])
        if head == "pilot":
            return self.pilot_command(" ".join(rest) if rest else None)
        if head == "here" and rest:
            return self._name_system(self.chain.current(), rest[0].upper()
                                     if _JCODE.match(rest[0]) else " ".join(rest))
        if head in ("k162", "k"):
            return self.file_k162(rest[0] if rest else None)
        if head in ("k162!", "k!"):
            return self.file_k162("!")
        if head == "rekey" and len(rest) == 2:
            return self._rekey(rest[0], rest[1], at)
        if len(rest) == 2 and rest[0] == "=" and _PREFIX.match(head):
            return self._rekey(head, rest[1], at)
        if head in ("cull", "cull!"):
            return self._cull(force=head == "cull!")
        if head == "sever" and rest:
            return self._sever(rest[0], at)
        if head == "fragment":
            return self._fragment(" ".join(rest) if rest else None)
        if head in ("discard", "discard!") and rest:
            return self._discard(" ".join(rest), force=head == "discard!")
        if _PREFIX.match(head) and rest:
            return self._sig_command(head, rest, at)
        return f"Unrecognised submission: {raw!r}. See `?` for accepted forms."

    # -- helpers -------------------------------------------------------------

    def _sweep(self, force: bool = False) -> str:
        if not self.last_report or not (
            self.last_report.despawned or (force and self.last_report.blocked)
        ):
            return "Nothing pending a sweep."
        targets = list(self.last_report.despawned)
        severed = []
        here = self.chain.current()
        here_path = list(self.chain.location)
        for prefix in list(self.last_report.blocked):
            # A despawned wormhole with mapped children: the hole collapsed.
            # Its far side becomes a fragment instead of being destroyed.
            severed.append(self._sever_conn(here_path, here, prefix))
        removed = apply_despawn(here, targets, force=force)
        self.last_report = None
        self._commit()
        parts = []
        if removed:
            parts.append(f"Struck from record: {' '.join(removed)}.")
        parts.extend(severed)
        return " ".join(parts) if parts else "Nothing swept."

    def _locate(self, prefix: str, at: str | None = None):
        """Resolve a signature prefix anywhere in the chain.

        Returns (path, system, sig). Preference order: an @System qualifier;
        the current system; a unique match chain-wide. Ambiguity is an error
        naming the candidate systems — the Bureau does not guess.
        """
        p = prefix.upper()[:3]
        matches: list[tuple[list[str], System]] = []

        def walk(path: list[str], system: System) -> None:
            if system.find_sig(p) is not None:
                matches.append((path, system))
            for conn in system.connections:
                walk(path + [conn.sig_prefix], conn.child)

        for ri, root in enumerate(self.chain.roots):
            walk([ri], root)
        if at is not None:
            matches = [m for m in matches if m[1].name.lower() == at.lower()]
            if not matches:
                raise ChainError(f"no signature {p!r} in {at}")
        if not matches:
            raise ChainError(f"no signature {p!r} anywhere on this chain")
        if len(matches) > 1:
            here = self.chain.current()
            preferred = [m for m in matches if m[1] is here]
            if preferred:
                matches = preferred
            else:
                names = ", ".join(m[1].name for m in matches)
                raise ChainError(f"{p} exists in {names} — qualify with @system")
        path, system = matches[0]
        return path, system, system.find_sig(p)

    def _connection_of(self, prefix: str, at: str | None):
        path, system, _sig = self._locate(prefix, at)
        conn = system.find_connection(prefix)
        if conn is None:
            raise ChainError(
                f"{prefix.upper()[:3]} in {system.name} is not an opened wormhole"
            )
        return system, conn

    def _eol(self, prefix: str, at: str | None = None) -> str:
        system, conn = self._connection_of(prefix, at)
        conn.eol = not conn.eol
        conn.eol_marked_at = utcnow() if conn.eol else None
        self._commit()
        state = "END OF LIFE (≤4h from now)" if conn.eol else "no longer EOL"
        return f"{conn.sig_prefix} ({system.name}) marked {state}."

    def _mass(self, prefix: str, at: str | None = None) -> str:
        system, conn = self._connection_of(prefix, at)
        cycle = [MassState.FRESH, MassState.REDUCED, MassState.CRITICAL]
        conn.mass = cycle[(cycle.index(conn.mass) + 1) % 3]
        self._commit()
        return f"{conn.sig_prefix} ({system.name}) mass: {conn.mass.value.upper()}."

    def _pair_return_from_first_scan(self, system) -> str:
        """The first deposit in a fresh system: a lone wormhole among the
        new sigs is almost always the way home — it is the first thing a
        pilot scans. Pairs the sig only; the type is never assumed, and
        `return <sig>` restates the pairing if the guess was wrong."""
        path = self.chain.location
        if len(path) <= 1:
            return ""
        parent = self.chain.system_at(path[:-1])
        inbound = parent.find_connection(path[-1])
        if inbound is None or inbound.return_prefix is not None:
            return ""
        holes = [
            s for s in system.sigs
            if s.group is SigGroup.WORMHOLE
            and system.find_connection(s.prefix) is None
        ]
        if len(holes) != 1:
            return ""
        inbound.return_prefix = holes[0].prefix
        return (
            f"{holes[0].prefix} filed as your return through "
            f"{inbound.sig_prefix} — sole hole in a first scan "
            f"(`return <sig>` to correct)"
        )

    def _unopened_holes(self, system, path) -> list[str]:
        """Scanned, unopened wormhole sigs that could lead somewhere new —
        the paired return hole leads home and is not a candidate."""
        paired = None
        if len(path) > 1:
            parent = self.chain.system_at(path[:-1])
            via = parent.find_connection(path[-1])
            if via is not None:
                paired = via.return_prefix
        return [
            s.prefix for s in system.sigs
            if s.group is SigGroup.WORMHOLE
            and system.find_connection(s.prefix) is None
            and s.prefix != paired
        ]

    def _unpair_return(self, at: str | None = None) -> str:
        """Strike a return pairing that was wrong — the current system's
        (or @system's) inbound hole goes back to claiming no sig as home."""
        if at is not None:
            path = self._find_system(at)
            if path is None:
                raise ChainError(f"no system '{at}' on this chain")
        else:
            path = list(self.chain.location)
        system = self.chain.system_at(path)
        if len(path) <= 1:
            raise ChainError(
                f"{system.name} is a fragment root — no inbound hole to unpair"
            )
        inbound = self.chain.system_at(path[:-1]).find_connection(path[-1])
        if inbound is None or inbound.return_prefix is None:
            return f"No return pairing on record for {system.name}."
        struck = inbound.return_prefix
        inbound.return_prefix = None
        self._commit()
        return (
            f"Pairing struck: {struck} no longer claims to be "
            f"{system.name}'s way home. `return <sig>` when you know it."
        )

    def _set_return(self, prefix: str, at: str | None = None,
                    code: str | None = None) -> str:
        """Explicitly pair a signature with the hole its system was entered
        through — never assumed, always stated. An optional type code read
        on this side (`return ina B274`) types the whole connection: the
        true type lives wherever it was read; the other end wears K162."""
        path, system, sig = self._locate(prefix, at)
        if len(path) <= 1:
            raise ChainError(
                f"{system.name} is a fragment root — no inbound hole to return through"
            )
        parent = self.chain.system_at(path[:-1])
        inbound = parent.find_connection(path[-1])
        sig.group = SigGroup.WORMHOLE
        inbound.return_prefix = sig.prefix
        typed = ""
        if code is not None:
            wh_type = lookup_wh_type(code)
            if wh_type is None or code.upper() == "K162":
                if code.upper() == "K162":
                    inbound.k162_end = "child"
                    typed = " Its K162 end is on this side."
                else:
                    raise ChainError(f"{code!r} is not a wormhole type")
            else:
                inbound.wh_type = wh_type.code
                inbound.k162_end = "parent"
                typed = (
                    f" True type {wh_type.code} read from this side — "
                    f"{parent.name}'s end is the K162."
                )
        self._commit()
        return (
            f"{sig.prefix} filed as the far side of {inbound.sig_prefix} "
            f"— paired with {parent.name}.{typed}"
        )

    def _sever_conn(self, path: list, system: System, prefix: str) -> str:
        """Core of a sever: detach the connection at `prefix` in `system`
        (located at `path`) into a free-floating fragment."""
        sig = self._require_prefix(system, prefix)
        conn = system.find_connection(sig.prefix)
        if conn is None:
            raise ChainError(f"{sig.prefix} is not an opened wormhole")
        child = conn.child
        system.connections.remove(conn)
        system.sigs.remove(sig)
        child.adrift_since = utcnow()
        self.chain.roots.append(child)
        new_ri = len(self.chain.roots) - 1
        inside = path + [sig.prefix]
        if self.chain.location[: len(inside)] == inside:
            # We were behind the collapse: our position moves to the fragment.
            self.chain.location = [new_ri] + self.chain.location[len(inside):]
        return (
            f"{sig.prefix} severed — {child.name} and everything behind it "
            f"is now fragment #{new_ri + 1}, adrift but on file."
        )

    def _sever(self, prefix: str, at: str | None = None) -> str:
        """Strike a dead hole but keep everything behind it as a free-floating
        fragment — the routine outcome of a mid-chain collapse."""
        path, system, _sig = self._locate(prefix, at)
        message = self._sever_conn(path, system, prefix)
        self._commit()
        return message

    def _fragment(self, arg: str | None) -> str:
        """File a new free-floating fragment: from a pending arrival, or by
        name (`fragment J123456` / `fragment Staging`)."""
        if arg:
            name = arg.upper() if _JCODE.match(arg) else arg
            if _JCODE.match(arg) and not name.startswith("J"):
                name = "J" + name
        elif self.pending_arrival is not None:
            name = self.pending_arrival[0]
        else:
            return (
                "Nothing to file: name it (`fragment J123456`) or arrive "
                "somewhere unmapped first."
            )
        system = System(name=name, adrift_since=utcnow())
        info = lookup_system(name)
        if info is not None:
            system.jclass = info.jclass
            system.statics = info.static_display
            system.effect = info.effect
        self.chain.roots.append(system)
        self.chain.location = [len(self.chain.roots) - 1]
        self.pending_arrival = None
        self._commit()
        return f"{name} filed as fragment #{len(self.chain.roots)} — ◉ YOU placed there."

    def _strike(self, args: list[str], at: str | None,
                force: bool = False, sig_only: bool = False) -> str:
        """One strike verb: each argument is a signature prefix, a fragment
        #number, or a fragment name — resolved in that order."""
        results = []
        for arg in args:
            if not sig_only:
                if arg.lstrip("#").isdigit():
                    results.append(self._discard(arg, force=force))
                    continue
            try:
                path, system, sig = self._locate(arg, at)
            except ChainError as sig_err:
                if sig_only:
                    raise
                try:
                    results.append(self._discard(arg, force=force))
                    continue
                except ChainError:
                    raise sig_err from None
            system.remove_sig(arg, force=force)
            lp = len(path)
            if (
                self.chain.location[:lp] == path
                and len(self.chain.location) > lp
                and self.chain.location[lp] == sig.prefix
            ):
                self.chain.location = list(path)
            results.append(f"{sig.prefix} struck from the record.")
        self._commit()
        return " ".join(results)

    def _discard(self, which: str, force: bool = False) -> str:
        """Strike an entire fragment, by number (as displayed) or by name."""
        ri: int | None = None
        try:
            ri = int(which.lstrip("#")) - 1
        except ValueError:
            wanted = which.lower()
            hits = [
                i for i, r in enumerate(self.chain.roots)
                if r.name.lower() == wanted or r.name.lower().startswith(wanted)
            ]
            if len(hits) > 1:
                names = ", ".join(self.chain.roots[i].name for i in hits)
                raise ChainError(f"ambiguous: {names}") from None
            if hits:
                ri = hits[0]
        if ri is None or not 0 <= ri < len(self.chain.roots):
            raise ChainError(f"no fragment {which!r} on this chain")
        if len(self.chain.roots) == 1:
            raise ChainError("this is the only fragment — the map must map something")
        if self.chain.location[0] == ri:
            raise ChainError("you are inside that fragment — leave before striking it")
        fragment = self.chain.roots[ri]
        if (fragment.sigs or fragment.connections) and not force:
            raise ChainError(
                f"fragment #{ri + 1} ({fragment.name}) still has mapped content "
                "— `strike!` to force"
            )
        self.chain.roots.pop(ri)
        if self.chain.location[0] > ri:
            self.chain.location[0] -= 1
        self._commit()
        return f"Fragment #{ri + 1} ({fragment.name}) struck from the record."

    def _adopt_fragment(self, system: System, path: list, prefix: str,
                        frag_ri: int) -> str:
        """Reattach a fragment as the destination of an opened signature."""
        if frag_ri == path[0]:
            raise ChainError(
                "that fragment contains this very system — adoption would "
                "close a loop the Bureau cannot file"
            )
        sig = self._require_prefix(system, prefix)
        fragment = self.chain.roots[frag_ri]
        sig.group = SigGroup.WORMHOLE
        fragment.adrift_since = None
        conn = Connection(sig_prefix=sig.prefix, child=fragment)
        system.connections.append(conn)
        self.chain.roots.pop(frag_ri)
        loc = self.chain.location
        if loc[0] == frag_ri:
            self.chain.location = path + [sig.prefix] + loc[1:]
        elif loc[0] > frag_ri:
            self.chain.location = [loc[0] - 1] + loc[1:]
        self._commit()
        return (
            f"{sig.prefix} ({system.name}) → {fragment.name} — fragment "
            "reattached; the record is whole again."
        )

    def _switch_chain(self, name: str) -> str:
        self.chain = self.store.load_latest(name) or Chain(name=name)
        self.store.save_active(name)
        self.store.commit(self.chain)
        self.view = "full"
        self.last_report = None
        self.dirty = True
        return f"Chain of custody: {name}."

    def _sig_command(self, prefix: str, rest: list[str], at: str | None = None) -> str:
        arg = rest[0]
        if _JCODE.match(arg):
            return self._open_jcode(prefix, arg, at)
        wh_type = lookup_wh_type(arg)
        if wh_type is not None and len(rest) == 1:
            return self._set_wh_type(prefix, wh_type.code, at)
        if len(rest) == 1:
            # A single token naming an adrift fragment adopts it — k-space
            # fragments (Vard, Knophtikoo) reattach as readily as J-codes.
            for ri, root in enumerate(self.chain.roots):
                if root.name.lower() == arg.lower():
                    path, system, _sig = self._locate(prefix, at)
                    if system.find_connection(prefix) is None:
                        return self._adopt_fragment(system, path, prefix, ri)
        label = " ".join(rest)
        _, system, sig = self._locate(prefix, at)
        sig.label = label
        self._commit()
        return f"{sig.prefix} ({system.name}) labelled {label!r}."

    def _open_at(self, system: System, prefix: str, dest: str, *,
                 jclass=None, statics=None, effect=None, wh_type=None) -> Connection:
        sig = self._require_prefix(system, prefix)
        if system.find_connection(prefix) is not None:
            raise ChainError(f"{sig.prefix} is already opened")
        sig.group = SigGroup.WORMHOLE
        child = System(name=dest, jclass=jclass, statics=statics, effect=effect)
        conn = Connection(sig_prefix=sig.prefix, child=child, wh_type=wh_type)
        system.connections.append(conn)
        return conn

    def _open_jcode(self, prefix: str, jcode: str, at: str | None = None) -> str:
        info = lookup_system(jcode)
        path, system, _sig = self._locate(prefix, at)
        dest = info.jcode if info is not None else (
            jcode.upper() if jcode.upper().startswith("J") else f"J{jcode}"
        )
        if system.find_connection(prefix) is None:
            for ri, root in enumerate(self.chain.roots):
                if root.name.upper() == dest.upper():
                    return self._adopt_fragment(system, path, prefix, ri)
        if info is not None:
            conn = self._open_at(
                system, prefix, info.jcode, jclass=info.jclass,
                statics=info.static_display, effect=info.effect,
            )
            self._commit()
            eff = f" · {info.effect}" if info.effect else ""
            return (
                f"{conn.sig_prefix} ({system.name}) → {info.jcode} "
                f"[{info.jclass}+{info.static_display}{eff}]."
            )
        name = jcode.upper() if jcode.upper().startswith("J") else f"J{jcode}"
        conn = self._open_at(system, prefix, name)
        self._commit()
        return f"{conn.sig_prefix} ({system.name}) → {name} [not in Bureau records]."

    def _require_prefix(self, system, prefix: str) -> Signature:
        sig = system.find_sig(prefix)
        if sig is None:
            raise ChainError(f"no signature {prefix.upper()[:3]!r} in {system.name}")
        return sig

    def _set_wh_type(self, prefix: str, code: str, at: str | None = None) -> str:
        wh_type = lookup_wh_type(code)
        _, system, _sig = self._locate(prefix, at)
        conn = system.find_connection(prefix)
        if code == "K162":
            # K162 is an end, not a type: this sig is the far side of a hole
            # someone opened INTO this system. Its true type is unknown until
            # read from the other side.
            if conn is None:
                conn = self._open_at(system, prefix, "?")
            conn.k162_end = "parent"
            conn.wh_type = None
            self._commit()
            return (
                f"{conn.sig_prefix} ({system.name}) is a K162 — opened from "
                "the far side; type reads over there."
            )
        if conn is None:
            conn = self._open_at(
                system, prefix, "?",
                jclass=wh_type.target_display if wh_type.target_class else None,
                wh_type=code,
            )
        else:
            conn.wh_type = code
        conn.k162_end = "child"  # true type read here ⇒ far side wears K162
        self._commit()
        life = f", {wh_type.lifetime_hours:g}h" if wh_type.lifetime_hours else ""
        return (
            f"{conn.sig_prefix} ({system.name}) typed {code} "
            f"(→{wh_type.target_display}{life})."
        )

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
        wanted = arg.lower()
        exact = [p for p in self.known_pilots if p.lower() == wanted]
        prefixed = [p for p in self.known_pilots if p.lower().startswith(wanted)]
        if not exact and len(prefixed) > 1:
            return f"Ambiguous: {', '.join(sorted(prefixed))}."
        pilot = exact[0] if exact else (prefixed[0] if prefixed else arg)
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
        if chain.roots[0].name == "HOME" and not chain.roots[0].connections:
            return self._name_system(chain.roots[0], name)

        for conn in current.connections:
            if conn.child.name == name:
                chain.location.append(conn.sig_prefix)
                self.pending_arrival = None
                self._commit(amend=True)
                return f"Followed you through {conn.sig_prefix} to {name}."

        if len(chain.location) > 1:
            parent = chain.system_at(chain.location[:-1])
            if parent.name == name:
                chain.location.pop()
                self.pending_arrival = None
                self._commit(amend=True)
                return f"Followed you back up to {name}."

        # Passages that could be the one you took: opened holes with unknown
        # destinations, plus scanned-but-unopened wormhole sigs. Exactly one
        # candidate → the record files itself; more → the pilot arbitrates.
        unknown = [c for c in current.connections if c.child.name == "?"]
        unopened = self._unopened_holes(current, chain.location)
        # When the arrival is an adrift fragment's ROOT, reattach the
        # fragment whole — this outranks merely relocating the marker.
        if len(unknown) == 1 and not unopened:
            conn = unknown[0]
            for ri, root in enumerate(chain.roots):
                if root.name.lower() == name.lower() and ri != chain.location[0]:
                    conn.child = root
                    root.adrift_since = None
                    chain.roots.pop(ri)
                    if chain.location[0] > ri:
                        chain.location[0] -= 1
                    chain.location.append(conn.sig_prefix)
                    self.pending_arrival = None
                    self._commit()
                    return (
                        f"Assumed you took {conn.sig_prefix} — fragment "
                        f"{name} reattached; the record is whole again."
                    )

        found = self._find_system(name)
        if found is not None:
            chain.location = found
            self.pending_arrival = None
            self._commit(amend=True)
            return f"Relocated ◉ YOU to {name} (elsewhere in the chain)."

        if len(unknown) == 1 and not unopened:
            conn = unknown[0]
            expected = conn.child.jclass
            self._name_system(conn.child, name)
            chain.location.append(conn.sig_prefix)
            self.pending_arrival = None
            self._commit()
            note = ""
            info = lookup_system(name)
            actual = info.jclass if info else None
            if expected and actual and expected != actual:
                note = (
                    f" ({conn.wh_type or conn.sig_prefix} books {expected}; "
                    f"{name} is {actual} — verify the type.)"
                )
            return (
                f"Assumed you took {conn.sig_prefix}: destination now on "
                f"record as {name}.{note}"
            )

        if not unknown and len(unopened) == 1:
            # One scanned hole, one unaccounted arrival: file it through —
            # no placeholder, no rekey, no keypress.
            self.pending_arrival = (name, list(chain.location))
            return self.file_k162(unopened[0])

        self.pending_arrival = (name, list(chain.location))
        if unknown or unopened:
            listing = " · ".join(
                [c.sig_prefix for c in unknown] + unopened
            )
            return (
                f"Arrived in UNMAPPED {name} — which passage out of "
                f"{current.name}? {listing}. Submit `k162 <sig>` or click "
                f"one in the dossier; `k162!` files a fresh hole."
            )
        return (
            f"Arrived in UNMAPPED {name}. Press k (or submit `k162`) to file it "
            f"as a K162 out of {current.name}."
        )

    def arrival_candidates(self) -> list[str]:
        """Sig prefixes in the pending origin that could be the hole just
        taken: typed holes with unknown destinations, then scanned-but-
        unopened wormhole sigs."""
        if self.pending_arrival is None:
            return []
        from_path = self.pending_arrival[1]
        origin = self.chain.system_at(from_path)
        out = [c.sig_prefix for c in origin.connections if c.child.name == "?"]
        out += [
            p for p in self._unopened_holes(origin, from_path)
            if p not in out
        ]
        return out

    def file_k162(self, via: str | None = None) -> str:
        """File a pending unmapped arrival — through the hole you actually
        took when the record can tell which one that was.

        `via` names the passage explicitly; None auto-selects when exactly
        one candidate exists; "!" insists on a fresh unscanned hole."""
        if self.pending_arrival is None:
            return "No unmapped arrival pending. The record is at peace."
        name, from_path = self.pending_arrival
        origin = self.chain.system_at(from_path)
        fresh = via == "!"
        candidates = self.arrival_candidates()
        if via and not fresh:
            picks = [c for c in candidates if c.upper() == via.upper()]
            if not picks:
                raise ChainError(
                    f"no unopened passage '{via.upper()}' out of {origin.name}"
                )
            via = picks[0]
        elif not fresh and len(candidates) == 1:
            via = candidates[0]
        elif not fresh and len(candidates) > 1:
            listing = " · ".join(candidates)
            return (
                f"UNFILED: {name} — which passage out of {origin.name}? "
                f"{listing}. Submit `k162 <sig>` (or click one in the "
                f"dossier); `k162!` files a fresh unscanned hole."
            )
        else:
            via = None
        if via is not None:
            conn = origin.find_connection(via)
            if conn is not None:
                # A typed hole whose far side was never confirmed.
                self._name_system(conn.child, name)
                self.chain.location = list(from_path) + [via]
                self.pending_arrival = None
                self._commit()
            else:
                info = lookup_system(name)
                saved = self.chain.location
                self.chain.location = list(from_path)
                try:
                    self.chain.open_connection(
                        via, info.jcode if info else name,
                        jclass=info.jclass if info else None,
                        statics=info.static_display if info else None,
                        effect=info.effect if info else None,
                        wh_type=None,
                    )
                except ChainError:
                    self.chain.location = saved
                    raise
                self.chain.location = list(from_path) + [via]
                self.pending_arrival = None
                self._commit()
            return f"Filed {name} through {via}. The record aligns."
        prefix = self._placeholder_prefix(origin)
        origin.sigs.append(
            Signature(sig_id=f"{prefix}-000", group=SigGroup.WORMHOLE,
                      label="hole (unscanned)")
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
                wh_type=None,
            )
        except ChainError:
            self.chain.location = saved_location
            raise
        self.chain.location = list(from_path) + [prefix]
        self.pending_arrival = None
        self._commit()
        return (
            f"Filed {name} via placeholder {prefix} — refile (`{prefix.lower()} "
            "= abc`) when you scan the real signature."
        )

    def find_matches(self, query: str) -> list[tuple]:
        """Tree-node data tuples matching a query: system names first,
        then signatures by prefix, site name, or label."""
        q = query.strip().lower()
        if not q:
            return []
        matches: list[tuple] = []
        queue: list[tuple[list, object]] = [
            ([ri], root) for ri, root in enumerate(self.chain.roots)
        ]
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
        queue = list(self.chain.roots)
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
        queue: list[tuple[list, object]] = [
            ([ri], root) for ri, root in enumerate(self.chain.roots)
        ]
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

    def _rekey(self, old: str, new: str, at: str | None = None) -> str:
        """Refile a signature under its real prefix — for K162 placeholders
        whose true signature has since been scanned. Preserves the connection
        and everything mapped behind it. Resolves anywhere in the chain."""
        if not _PREFIX.match(new):
            raise ChainError(f"{new!r} is not a signature prefix")
        path, here, sig = self._locate(old, at)
        new_prefix = new.upper()[:3]
        old_prefix = sig.prefix
        conn = here.find_connection(old_prefix)
        target = here.find_sig(new_prefix)

        if target is not None:
            # The real signature is already on file (pasted after scanning):
            # absorb the placeholder into it. The scanned record keeps its
            # true id, name, and signal; the connection re-points.
            target_conn = here.find_connection(new_prefix)
            if target_conn is not None:
                # Two connections merge only when the target's far side is an
                # empty unknown — the duplicate-sibling case.
                if target_conn.child.name == "?" and not (
                    target_conn.child.sigs or target_conn.child.connections
                ):
                    if conn is None:
                        raise ChainError(
                            f"{old_prefix} has no connection to merge into "
                            f"{new_prefix}"
                        )
                    target_conn.child = conn.child
                    if not target_conn.wh_type:
                        target_conn.wh_type = conn.wh_type
                    if not target_conn.return_prefix:
                        target_conn.return_prefix = conn.return_prefix
                    here.connections.remove(conn)
                    here.sigs.remove(sig)
                    self._fix_location(path, old_prefix, new_prefix)
                    self._commit()
                    return (
                        f"{old_prefix} merged into {new_prefix} — the unknown "
                        f"destination is struck; {target_conn.child.name} stands."
                    )
                raise ChainError(
                    f"{new_prefix} is itself an opened wormhole — refile "
                    "would merge two connections"
                )
            if target.group not in (SigGroup.WORMHOLE, SigGroup.UNKNOWN):
                raise ChainError(
                    f"{new_prefix} is filed as a {target.group.value}, not a "
                    "wormhole — check the prefix"
                )
            here.sigs.remove(sig)
            target.group = SigGroup.WORMHOLE
            if sig.label and sig.label not in ("K162 (unscanned)", "hole (unscanned)"):
                target.label = target.label or sig.label
            message = (
                f"{old_prefix} absorbed into {new_prefix} — the placeholder "
                "is struck, the connection stands."
            )
        else:
            sig.sig_id = f"{new_prefix}-000"
            if sig.label in ("K162 (unscanned)", "hole (unscanned)"):
                sig.label = ""
            message = f"{old_prefix} refiled as {new_prefix}. The record forgives."

        if conn is not None:
            conn.sig_prefix = new_prefix
        self._fix_location(path, old_prefix, new_prefix)
        self._commit()
        return message

    def _fix_location(self, path: list[str], old_prefix: str, new_prefix: str) -> None:
        """If the renamed connection lies on the location path, follow it."""
        lp = len(path)
        if (
            self.chain.location[:lp] == path
            and len(self.chain.location) > lp
            and self.chain.location[lp] == old_prefix
        ):
            self.chain.location[lp] = new_prefix

    def _cull(self, force: bool = False) -> str:
        """Strike connections past their book lifetime (EXPIRED in the tree)."""
        from vagari.model.lifetime import LifeStatus, assess

        expired: list[tuple[list, System, str]] = []

        def walk(path: list, system: System) -> None:
            for conn in list(system.connections):
                if assess(conn).status is LifeStatus.EXPIRED:
                    expired.append((path, system, conn.sig_prefix))
                walk(path + [conn.sig_prefix], conn.child)

        for ri, root in enumerate(self.chain.roots):
            walk([ri], root)
        if not expired:
            return "Nothing past its book lifetime anywhere on the chain."
        removed, blocked = [], []
        for path, system, prefix in expired:
            try:
                system.remove_sig(prefix, force=force)
                removed.append(f"{prefix} ({system.name})")
            except ChainError:
                blocked.append(self._sever_conn(path, system, prefix))
        if removed or blocked:
            self._commit()
        parts = []
        if removed:
            parts.append(f"Culled: {' '.join(removed)}.")
        if blocked:
            parts.extend(blocked)
        return " ".join(parts)

    # -- activity history (auto-recon sampling) ------------------------------

    def sample_activity(self, cap: int = 24) -> list[str]:
        """Record a per-system PvP-kill sample for every system in the chain.
        Returns watchtower alerts: systems that just turned hostile."""
        systems: list = []

        def walk(system) -> None:
            systems.append(system)
            for conn in system.connections:
                walk(conn.child)

        for root in self.chain.roots:
            walk(root)
        alerts: list[str] = []
        for system in systems:
            info = lookup_system(system.name)
            if info is None:
                continue
            act = self.activity.get(info.system_id)
            pvp = (act.ship_kills + act.pod_kills) if act else 0
            history = self.activity_history.setdefault(info.system_id, [])
            was_quiet = not history or history[-1] == 0
            history.append(pvp)
            del history[:-cap]
            if pvp > 0 and was_quiet and len(history) > 1:
                alerts.append(
                    f"{system.name} ({pvp} PvP kill{'s' if pvp != 1 else ''} "
                    "in the last hour)"
                )
        return alerts

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

    def homeward(self) -> str:
        """The route from ◉ YOU back to the root, door by door — the return
        sig where one is on file, otherwise the far side of the inbound hole."""
        loc = self.chain.location
        if len(loc) <= 1:
            here = self.chain.current().name
            return f"You are at the top of this fragment — {here}."
        steps = []
        for i in range(len(loc), 1, -1):
            system = self.chain.system_at(loc[:i])
            parent = self.chain.system_at(loc[: i - 1])
            conn = parent.find_connection(loc[i - 1])
            door = (
                conn.return_prefix
                if conn is not None and conn.return_prefix
                else f"far side of {loc[i - 1]}"
            )
            steps.append(f"{system.name} ↩ {door}")
        steps.append(self.chain.system_at([loc[0]]).name)
        jumps = len(loc) - 1
        return (
            f"HOMEWARD ({jumps} jump{'s' if jumps != 1 else ''}): "
            + " → ".join(steps)
        )

    def breadcrumb(self) -> str:
        system = self.chain.system_at([self.chain.location[0]])
        names = [system.name]
        for prefix in self.chain.location[1:]:
            system = system.find_connection(prefix).child
            names.append(system.name)
        return " ▸ ".join(names)
