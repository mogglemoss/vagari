"""Paste reconciliation: the paste is the source of truth.

`add` semantics: merge the paste into the current system, never destroying
information — signal only rises, group/name only fill in or improve, user
labels always survive.

`lazy` semantics: additionally report sigs that are missing from the paste as
despawn candidates. Nothing is deleted here; `apply_despawn` does that, and
sigs whose connection still has mapped children are blocked from the sweep.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from vagari.model.chain import ChainError, Signature, SigGroup, System, utcnow
from vagari.parsers.scanner import ScanLine


@dataclass
class ReconcileReport:
    new: list[str] = field(default_factory=list)        # prefixes created
    updated: list[str] = field(default_factory=list)    # prefixes that gained info
    despawned: list[str] = field(default_factory=list)  # lazy: deletion candidates
    blocked: list[str] = field(default_factory=list)    # lazy: protected by children


def _merge(sig: Signature, line: ScanLine, now: datetime) -> bool:
    """Fold a scan line into an existing sig. Returns True if info improved."""
    improved = False
    sig.last_seen = now
    if line.signal > sig.signal:
        sig.signal = line.signal
        improved = True
    if line.group is not SigGroup.UNKNOWN and line.group is not sig.group:
        sig.group = line.group
        improved = True
    if line.name and line.name != sig.name:
        sig.name = line.name
        improved = True
    return improved


def reconcile(
    system: System,
    lines: list[ScanLine],
    *,
    lazy: bool = False,
    now: datetime | None = None,
) -> ReconcileReport:
    now = now or utcnow()
    report = ReconcileReport()
    seen: set[str] = set()

    for line in lines:
        if not line.is_signature:
            continue  # anomalies are not part of the sig list
        prefix = line.sig_id[:3]
        seen.add(prefix)
        sig = system.find_sig(prefix)
        if sig is None:
            system.sigs.append(
                Signature(
                    sig_id=line.sig_id,
                    group=line.group,
                    name=line.name,
                    signal=line.signal,
                    first_seen=now,
                    last_seen=now,
                )
            )
            report.new.append(prefix)
        elif _merge(sig, line, now):
            report.updated.append(prefix)

    if lazy:
        for sig in system.sigs:
            if sig.prefix in seen:
                continue
            conn = system.find_connection(sig.prefix)
            if conn is not None and (conn.child.sigs or conn.child.connections):
                report.blocked.append(sig.prefix)
            else:
                report.despawned.append(sig.prefix)

    return report


def apply_despawn(system: System, prefixes: list[str], *, force: bool = False) -> list[str]:
    """Delete the given sigs; returns the prefixes actually removed."""
    removed: list[str] = []
    for prefix in prefixes:
        try:
            system.remove_sig(prefix, force=force)
        except ChainError:
            continue
        removed.append(prefix)
    return removed
