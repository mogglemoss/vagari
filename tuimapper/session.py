"""Session: the engine-facing layer the UI drives.

Owns the live Chain, the Store, the view mode, and the command grammar.
Pure Python — fully testable without Textual.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from tuimapper.model.chain import Chain, ChainError, MassState
from tuimapper.model.reconcile import ReconcileReport, apply_despawn, reconcile
from tuimapper.model.store import Store
from tuimapper.parsers.catalog import lookup_system, lookup_wh_type
from tuimapper.parsers.scanner import parse_scan

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

    # -- lifecycle -----------------------------------------------------------

    @classmethod
    def open(cls, store: Store, name: str = "home") -> Session:
        chain = store.load_latest(name)
        if chain is None:
            chain = Chain(name=name)
            store.commit(chain)
        return cls(store=store, chain=chain)

    def _commit(self) -> None:
        self.store.commit(self.chain)
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
            self._commit()
            return f"Relocated to {self.chain.current().name}."
        if head == "up":
            self.chain.up()
            self._commit()
            return f"Relocated to {self.chain.current().name}."
        if head == "nav" and rest:
            for prefix in rest:
                self.chain.nav(prefix)
            self._commit()
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

    def jump(self, path: list[str]) -> str:
        """Set the current location to an already-mapped path (tree navigation)."""
        self.chain.system_at(path)  # validates
        self.chain.location = list(path)
        self._commit()
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
