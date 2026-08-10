"""The chain rendered as a Textual Tree."""

from __future__ import annotations

from datetime import datetime

from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from vagari.model.chain import Connection, Signature, SigGroup, System, utcnow
from vagari.model.lifetime import LifeStatus, assess, hours_text
from vagari.session import Session

from vagari.glyphs import GLYPHS as _GLYPHS
from vagari.glyphs import KIND_WIDTH, kind_word

RUST = "#C15F3C"
MUTED = "#7a756e"
TEXT = "#e8e6e3"
DIM = "#8A3820"
WARN = "#d4a017"
FADED = "#4a453e"      # stale filings
FLARE = "#e8a559"      # fresh filings

NEW_MINUTES = 15       # ● marker while a sig is this fresh
STALE_HOURS = 6        # dimmed once unconfirmed this long


def age_text(since: datetime, now: datetime | None = None) -> str:
    """'3h12m' style age."""
    delta = (now or utcnow()) - since
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h{minutes % 60:02d}m"


def _visible(sig: Signature, view: str) -> bool:
    """Themed views hide unopened wormhole sigs; OPENED wormholes always
    render — child systems hang from them, so they are structure, not noise.
    (That structural rendering happens in _fill, independent of this.)"""
    if view == "paths":
        return sig.group is SigGroup.WORMHOLE
    if view == "sites":
        return sig.group in (SigGroup.RELIC, SigGroup.DATA)
    if view == "gas":
        return sig.group is SigGroup.GAS
    if view == "combat":
        return sig.group is SigGroup.COMBAT
    return True


def system_label(system: System, here: bool, kinfo=None,
                 pilots: tuple = (), now: datetime | None = None) -> str:
    parts = [f"[bold {TEXT}]{system.name}[/bold {TEXT}]"]
    meta = []
    if system.jclass:
        meta.append(system.jclass + (f"+{system.statics}" if system.statics else ""))
    if system.effect:
        meta.append(system.effect)
    if kinfo is not None:
        sec_color = {"H": TEXT, "L": WARN, "N": DIM}[kinfo.band]
        parts.append(f"[{sec_color}]{kinfo.sec_display}[/{sec_color}]")
        meta.append(kinfo.region)
    if meta:
        parts.append(f"[{MUTED}]{' · '.join(meta)}[/{MUTED}]")
    if system.sigs:
        freshest = max(s.last_seen for s in system.sigs)
        if ((now or utcnow()) - freshest).total_seconds() / 3600 >= STALE_HOURS:
            parts.append(
                f"[{FADED}](scanned {age_text(freshest, now)} ago)[/{FADED}]"
            )
    if here:
        parts.append(f"[bold {RUST}]◉ YOU[/bold {RUST}]")
    for name in pilots:
        parts.append(f"[{WARN}]◎ {name}[/{WARN}]")
    return "  ".join(parts)


def return_label(sig: Signature, parent_name: str) -> str:
    """The far side of the hole we came through — the way home."""
    kind_cell = f"[{RUST}]{'RETURN':<{KIND_WIDTH}}[/{RUST}]"
    return (
        f"[{RUST}]○[/{RUST}] {kind_cell} [{TEXT}]{sig.prefix}[/{TEXT}] "
        f"[{MUTED}]{sig.label or sig.name or 'K162'}[/{MUTED}]  "
        f"[{RUST}]↩ {parent_name}[/{RUST}]"
    )


def sig_label(sig: Signature, conn: Connection | None,
              now: datetime | None = None) -> str:
    now = now or utcnow()
    age_minutes = (now - sig.first_seen).total_seconds() / 60
    stale_hours = (now - sig.last_seen).total_seconds() / 3600
    stale = conn is None and stale_hours >= STALE_HOURS

    glyph = _GLYPHS[sig.group]
    flag = f"[bold {WARN}]![/bold {WARN}]" if sig.flagged else ""
    name = sig.label or sig.name
    if not name and sig.signal < 100:
        name = f"({sig.signal:.0f}%)"
    color = RUST if sig.group is SigGroup.WORMHOLE else MUTED
    prefix_color = FADED if stale else TEXT
    name_color = FADED if stale else MUTED
    kind = kind_word(sig.group, sig.name)
    kind_color = (
        f"bold {WARN}" if kind == "GHOST"
        else RUST if sig.group is SigGroup.WORMHOLE
        else FADED if stale or sig.group is SigGroup.UNKNOWN
        else MUTED
    )
    kind_cell = f"[{kind_color}]{kind:<{KIND_WIDTH}}[/{kind_color}]"
    text = (
        f"[{color}]{glyph}[/{color}] {kind_cell} "
        f"[{prefix_color}]{sig.prefix}[/{prefix_color}]{flag}"
    )
    if name:
        text += f" [{name_color}]{name}[/{name_color}]"
    if age_minutes <= NEW_MINUTES:
        text += f" [{FLARE}]●[/{FLARE}]"
    if stale:
        text += f" [{FADED}]({age_text(sig.last_seen, now)} unconfirmed)[/{FADED}]"
    if conn is not None:
        badges = []
        if conn.k162_end == "parent":
            badges.append("K162" + (f"({conn.wh_type})" if conn.wh_type else ""))
        elif conn.wh_type:
            badges.append(conn.wh_type)
        life = assess(conn)
        if life.remaining_hours is not None:
            life_color = {
                LifeStatus.HEALTHY: MUTED,
                LifeStatus.WANING: WARN,
                LifeStatus.EXPIRED: DIM,
                LifeStatus.EOL: DIM,
            }.get(life.status, MUTED)
            label = "EXPIRED?" if life.status is LifeStatus.EXPIRED else (
                f"≤{hours_text(life.remaining_hours)}"
            )
            badges.append(f"[{life_color}]{label}[/{life_color}]")
        else:
            badges.append(age_text(conn.opened_at))
        if conn.mass.value != "fresh":
            badges.append(conn.mass.value.upper())
        if conn.eol:
            badges.append(f"[bold {DIM}]EOL[/bold {DIM}]")
        text += f"  [{MUTED}]{' '.join(badges)}[/{MUTED}]"
    return text


class ChainTree(Tree):
    """Tree of systems and signatures. Node data:

    ("system", path)           — a system, at `path` (list of sig prefixes)
    ("sig", path, prefix)      — a signature within the system at `path`
    """

    def __init__(self, session: Session, **kwargs) -> None:
        super().__init__("root", **kwargs)
        self.session = session
        self.show_root = False  # the tree root is the chain; fragments are top-level
        self.guide_depth = 3
        # Mouse policy: a single click selects (inspection); only a
        # double-click navigates. Enter always navigates.
        self.suppress_click_nav = False

    def on_click(self, event) -> None:
        self.suppress_click_nav = getattr(event, "chain", 1) < 2

    def move_to_data(self, data: tuple) -> bool:
        def walk(node):
            if node.data == data:
                return node
            for child in node.children:
                found = walk(child)
                if found is not None:
                    return found
            return None

        node = walk(self.root)
        if node is not None:
            def apply() -> None:
                self.move_cursor(node)
                self.scroll_to_node(node)

            apply()
            # Freshly rebuilt nodes may not have layout lines yet; re-apply
            # once the next refresh has assigned them.
            self.call_after_refresh(apply)
            return True
        return False

    def _fleet(self, system_name: str) -> tuple:
        return tuple(
            p for p, s in sorted(self.session.known_pilots.items())
            if s == system_name and p != self.session.pilot_lock
        )

    @staticmethod
    def _key(data) -> tuple | None:
        if data is None:
            return None
        if data[0] == "system":
            return ("system", tuple(data[1]))
        return ("sig", tuple(data[1]), data[2])

    def _collapsed_keys(self) -> set:
        collapsed = set()

        def walk(node) -> None:
            if node.children and not node.is_expanded:
                key = self._key(node.data)
                if key is not None:
                    collapsed.add(key)
            for child in node.children:
                walk(child)

        walk(self.root)
        return collapsed

    def rebuild(self) -> None:
        chain = self.session.chain
        cursor_data = self.cursor_node.data if self.cursor_node else None
        collapsed = self._collapsed_keys()
        self.clear()
        self.root.set_label(f"[{MUTED}]chain {chain.name}[/{MUTED}]")
        self.root.data = None
        for ri, fragment in enumerate(chain.roots):
            adrift = ""
            if len(chain.roots) > 1:
                adrift = f" [{DIM}]#{ri + 1}[/{DIM}]"
            if fragment.adrift_since is not None:
                adrift += (
                    f" [{DIM}]· adrift {age_text(fragment.adrift_since)}[/{DIM}]"
                )
            elif ri > 0:
                adrift += f" [{DIM}]· adrift[/{DIM}]"
            node = self.root.add(
                system_label(fragment, here=chain.location == [ri],
                             kinfo=self.session.kspace.get(fragment.name),
                             pilots=self._fleet(fragment.name))
                + adrift,
                data=("system", [ri]),
            )
            self._fill(node, fragment, [ri])
        self.root.expand_all()
        if collapsed:
            def restore(node) -> None:
                if self._key(node.data) in collapsed:
                    node.collapse()
                for child in node.children:
                    restore(child)

            restore(self.root)
        if cursor_data is not None:
            self._restore_cursor(cursor_data)

    def _restore_cursor(self, data: tuple) -> None:
        self.move_to_data(data)

    def _fill(self, node: TreeNode, system: System, path: list[str],
              via: Connection | None = None, parent_name: str = "") -> None:
        chain = self.session.chain
        for sig in system.sigs:
            conn = system.find_connection(sig.prefix)
            if conn is None:
                if via is not None and sig.prefix == via.return_prefix:
                    node.add_leaf(
                        return_label(sig, parent_name),
                        data=("sig", path, sig.prefix),
                    )
                elif _visible(sig, self.session.view):
                    node.add_leaf(sig_label(sig, None), data=("sig", path, sig.prefix))
                continue
            sig_node = node.add(sig_label(sig, conn), data=("sig", path, sig.prefix))
            child_path = path + [sig.prefix]
            child_node = sig_node.add(
                system_label(conn.child, here=chain.location == child_path,
                             kinfo=self.session.kspace.get(conn.child.name),
                             pilots=self._fleet(conn.child.name)),
                data=("system", child_path),
            )
            self._fill(child_node, conn.child, child_path,
                       via=conn, parent_name=system.name)
