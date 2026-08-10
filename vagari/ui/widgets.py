"""Shared UI widgets — the header and its resident."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

# The Bureau's anglerfish-robot — same genus as HARUSPEX's, different posting.
# The esca (antenna lure) cycles: slow pulse, brief flare, slow fade.
_ESCA_FRAMES = [
    "#C15F3C",  # rest
    "#C15F3C",  # rest
    "#e8a559",  # flare
    "#C15F3C",  # rest
    "#8A3820",  # fade
    "#C15F3C",  # recover
]


def _mascot(esca_color: str) -> str:
    """Compact 3-line robot head, esca blinking at the antenna tip."""
    return (
        f"     [bold {esca_color}]·[/bold {esca_color}]\n"
        f" [#7a756e]╭───[/#7a756e][{esca_color}]●[/{esca_color}][#7a756e]───╮[/#7a756e]\n"
        f"[#7a756e]([/#7a756e][#7a756e]│   [/#7a756e][#e8e6e3]◉[/#e8e6e3][#7a756e]   │)[/#7a756e]"
    )


class VagariHeader(Horizontal):
    """Persistent header: title, breadcrumb, and the animated mascot."""

    DEFAULT_CSS = """
    VagariHeader {
        height: 3;
        background: #201d18;
        padding: 0 2;
        dock: top;
    }
    #header-titles {
        width: 1fr;
        height: 3;
    }
    #header-title-row {
        height: 1;
    }
    #header-title {
        width: 1fr;
        height: 1;
        content-align: left middle;
    }
    #header-clock {
        width: 11;
        height: 1;
        color: #7a756e;
        content-align: right middle;
    }
    #header-breadcrumb {
        height: 1;
        color: #e8e6e3;
        content-align: left middle;
    }
    #header-status {
        height: 1;
        color: #7a756e;
        content-align: left middle;
    }
    #header-mascot {
        width: 13;
        height: 3;
        content-align: left top;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="header-titles"):
            with Horizontal(id="header-title-row"):
                yield Static(
                    "[bold #C15F3C]VAGARI[/bold #C15F3C] "
                    "[#7a756e]· ANOIKIS CARTOGRAPHIC BUREAU · Chain Custody Instrument[/#7a756e]",
                    id="header-title",
                )
                yield Static("", id="header-clock")
            yield Static("", id="header-breadcrumb")
            yield Static("", id="header-status")
        yield Static(_mascot(_ESCA_FRAMES[0]), id="header-mascot")

    def on_mount(self) -> None:
        self._esca_frame = 0
        self.set_interval(0.55, self._tick_esca)
        self._tick_clock()
        self.set_interval(10, self._tick_clock)

    def _tick_clock(self) -> None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        self.query_one("#header-clock", Static).update(
            f"[#7a756e]EVE {now:%H:%M}[/#7a756e]"
        )

    def update_state(
        self,
        chain_name: str,
        breadcrumb: str,
        pending_arrival: str | None = None,
        pilot: str | None = None,
        follow_active: bool = False,
        despawned: list | None = None,
    ) -> None:
        self.query_one("#header-breadcrumb", Static).update(
            f"[#7a756e]chain[/#7a756e] [#e8e6e3]{chain_name}[/#e8e6e3] "
            f"[#7a756e]·[/#7a756e] [#e8e6e3]{breadcrumb}[/#e8e6e3]"
            + (f" [#7a756e]· following[/#7a756e] [#e8e6e3]{pilot}[/#e8e6e3]"
               if pilot else "")
        )
        badges = []
        if pending_arrival:
            # Sticky until filed or superseded — the status line is transient
            # and auto-recon used to bury this prompt.
            badges.append(
                f"[bold #C15F3C][@click=app.file_k162]UNMAPPED: "
                f"{pending_arrival} — press k or click to file[/][/bold #C15F3C]"
            )
        if despawned:
            names = " ".join(despawned)
            badges.append(
                f"[bold #d4a017][@click=app.sweep]DESPAWNED: {names} — "
                f"press s or click to sweep[/][/bold #d4a017]"
            )
        if follow_active and pilot is None and not pending_arrival:
            # Cold start with no lock: without this, an idle multibox fleet
            # makes follow-me look broken — nothing moves until someone jumps.
            badges.append(
                "[#d4a017]NOT FOLLOWING — submit `pilot <name>` to choose "
                "(first pilot to jump otherwise)[/#d4a017]"
            )
        self.query_one("#header-status", Static).update("  ".join(badges))

    def flare(self) -> None:
        """Flare the esca out of cycle — something just happened."""
        self._esca_frame = 1  # next tick lands on the flare frame
        self.query_one("#header-mascot", Static).update(_mascot("#e8a559"))

    def _tick_esca(self) -> None:
        self._esca_frame = (self._esca_frame + 1) % len(_ESCA_FRAMES)
        self.query_one("#header-mascot", Static).update(
            _mascot(_ESCA_FRAMES[self._esca_frame])
        )
