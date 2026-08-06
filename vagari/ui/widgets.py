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
    #header-title {
        height: 1;
        content-align: left middle;
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
            yield Static(
                "[bold #C15F3C]VAGARI[/bold #C15F3C] "
                "[#7a756e]· ANOIKIS CARTOGRAPHIC BUREAU · Chain Custody Instrument[/#7a756e]",
                id="header-title",
            )
            yield Static("", id="header-breadcrumb")
            yield Static("", id="header-status")
        yield Static(_mascot(_ESCA_FRAMES[0]), id="header-mascot")

    def on_mount(self) -> None:
        self._esca_frame = 0
        self.set_interval(0.55, self._tick_esca)

    def update_state(self, chain_name: str, breadcrumb: str, lazy_armed: bool) -> None:
        self.query_one("#header-breadcrumb", Static).update(
            f"[#7a756e]chain[/#7a756e] [#e8e6e3]{chain_name}[/#e8e6e3] "
            f"[#7a756e]·[/#7a756e] [#e8e6e3]{breadcrumb}[/#e8e6e3]"
        )
        self.query_one("#header-status", Static).update(
            "[bold #d4a017]LAZY ARMED[/bold #d4a017]" if lazy_armed else ""
        )

    def _tick_esca(self) -> None:
        self._esca_frame = (self._esca_frame + 1) % len(_ESCA_FRAMES)
        self.query_one("#header-mascot", Static).update(
            _mascot(_ESCA_FRAMES[self._esca_frame])
        )
