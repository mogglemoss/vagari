"""Plain-text chain export — for fleet channels, corp Discord, and the file.

bashmapper's tree output was inherently copy-pasteable; this restores that
property. No markup, no colour: the recipient's client is not the Bureau's
problem.
"""

from __future__ import annotations

from vagari.glyphs import GLYPHS, KIND_WIDTH, YOU, kind_word
from vagari.model.chain import Chain, Signature, SigGroup, System
from vagari.model.lifetime import LifeStatus, assess, hours_text


def _sig_line(system: System, sig: Signature) -> str:
    conn = system.find_connection(sig.prefix)
    parts = [
        GLYPHS[sig.group],
        f"{kind_word(sig.group, sig.name):<{KIND_WIDTH}}",
        sig.prefix + ("!" if sig.flagged else ""),
    ]
    name = sig.label or sig.name
    if name:
        parts.append(name)
    elif sig.signal < 100:
        parts.append(f"({sig.signal:.0f}%)")
    if conn is not None:
        badges = []
        if conn.wh_type:
            badges.append(conn.wh_type)
        life = assess(conn)
        if life.remaining_hours is not None:
            badges.append(
                "EXPIRED?" if life.status is LifeStatus.EXPIRED
                else f"≤{hours_text(life.remaining_hours)}"
            )
        if conn.mass.value != "fresh":
            badges.append(conn.mass.value.upper())
        if conn.eol:
            badges.append("EOL")
        if badges:
            parts.append("[" + " ".join(badges) + "]")
    return " ".join(parts)


def _system_line(system: System, here: bool) -> str:
    parts = [system.name]
    meta = []
    if system.jclass:
        meta.append(system.jclass + (f"+{system.statics}" if system.statics else ""))
    if system.effect:
        meta.append(system.effect)
    if meta:
        parts.append(f"[{' · '.join(meta)}]")
    if here:
        parts.append(YOU)
    return " ".join(parts)


def export_text(chain: Chain, view: str = "full") -> str:
    """Render the chain as an indented plain-text tree."""

    def visible(sig: Signature) -> bool:
        if view == "paths":
            return sig.group is SigGroup.WORMHOLE
        if view == "gas":
            return sig.group in (SigGroup.WORMHOLE, SigGroup.GAS)
        return True

    lines: list[str] = []

    def walk(system: System, path: list[str], prefix: str) -> None:
        sigs = [s for s in system.sigs if visible(s) or system.find_connection(s.prefix)]
        for i, sig in enumerate(sigs):
            last = i == len(sigs) - 1
            branch, carry = ("└─ ", "   ") if last else ("├─ ", "│  ")
            lines.append(prefix + branch + _sig_line(system, sig))
            conn = system.find_connection(sig.prefix)
            if conn is not None:
                child_path = path + [sig.prefix]
                lines.append(
                    prefix + carry + "└→ "
                    + _system_line(conn.child, here=chain.location == child_path)
                )
                walk(conn.child, child_path, prefix + carry + "   ")

    lines.append(_system_line(chain.root, here=chain.location == []))
    walk(chain.root, [], "")
    lines.append("")
    lines.append(f"— VAGARI · chain {chain.name} · Anoikis Cartographic Bureau")
    return "\n".join(lines)
