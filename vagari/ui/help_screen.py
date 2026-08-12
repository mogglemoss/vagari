"""The instrument reference — generated from the command registry so the
help, the palette, and the suggester can never drift apart."""

from __future__ import annotations

import textwrap

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from vagari.commands import CATEGORIES, REGISTRY

_RUST = "#C15F3C"
_MUTED = "#7a756e"
_TEXT = "#e8e6e3"
_LINE = "#3a3530"

_GRAMMAR_WIDTH = 18
_HELP_WIDTH = 30

_PROSE = {
    "drive": (
        f"  [{_TEXT}]Paste scan telemetry any time the map\n"
        f"  has focus — no mode, no prompt.\n"
        f"  Bold keys act on the map. [bold]Tab[/bold] or [bold]:[/bold]\n"
        f"  moves to the submission line; [bold]Enter[/bold]\n"
        f"  files it; [bold]Esc[/bold] or [bold]Tab[/bold] returns. [bold]→[/bold]\n"
        f"  accepts the ghost suggestion.\n"
        f"  Click selects · double-click proceeds ·\n"
        f"  dossier links act on the selection.[/{_TEXT}]"
    ),
    "follow": (
        f"  [{_MUTED}]jump in-game and ◉ YOU follows via your\n"
        f"  chatlogs; fleetmates appear as ◎ Name[/{_MUTED}]"
    ),
}

_LEGEND = (
    f"  [{_RUST}]○[/{_RUST}] wormhole   [{_MUTED}]▸ combat  ◇ data  ◈ relic[/{_MUTED}]\n"
    f"  [{_MUTED}]≈ gas  ▪ ore  · unresolved  ![/{_MUTED}] flagged"
)

_PROCEDURE = [
    "undock and jump — your first system names the root",
    "paste probe-scanner rows; anywhere, any time",
    "a first scan's lone hole pairs itself as your return",
    "type a hole (xpa Z060) or click a candidate in its dossier",
    "jump it — the map follows; a sole scanned hole files itself",
    "scan · jump · repeat — sweep strikes despawns, home leads back",
]


def _rule_line(title: str) -> str:
    bar = "─" * max(3, 40 - len(title))
    return (
        f"[{_LINE}]──[/{_LINE}] [bold {_MUTED}]{title}[/bold {_MUTED}] "
        f"[{_LINE}]{bar}[/{_LINE}]"
    )


def _escape(text: str) -> str:
    """Literal brackets in grammar ('fragment [name]') must not be tags."""
    return text.replace("[", "\\[")


def _entry_lines(grammar: str, keys: str, help_text: str) -> list[str]:
    head = _escape(grammar)
    help_text = _escape(help_text)
    if keys:
        head += f" · {keys}"
    wrapped = textwrap.wrap(help_text, _HELP_WIDTH) or [""]
    pad = " " * (_GRAMMAR_WIDTH + 3)
    lines = []
    if len(head) <= _GRAMMAR_WIDTH:
        lines.append(
            f"  [bold]{head:<{_GRAMMAR_WIDTH}}[/bold] "
            f"[{_MUTED}]{wrapped[0]}[/{_MUTED}]"
        )
        rest = wrapped[1:]
    else:
        lines.append(f"  [bold]{head}[/bold]")
        rest = wrapped
    for w in rest:
        lines.append(f"{pad}[{_MUTED}]{w}[/{_MUTED}]")
    return lines


def build_reference() -> str:
    out = [
        f"[bold {_RUST}]ANOIKIS CARTOGRAPHIC BUREAU[/bold {_RUST}]",
        f"[{_MUTED}]Department of Spatial Relations · instrument "
        f"reference[/{_MUTED}]",
        "",
        _rule_line("field procedure"),
    ]
    for n, step in enumerate(_PROCEDURE, 1):
        out.append(
            f"  [{_RUST}]{n}[/{_RUST}]  [{_TEXT}]{_escape(step)}[/{_TEXT}]"
        )
    for key, title in CATEGORIES:
        out.append("")
        out.append(_rule_line(title))
        if key in _PROSE:
            out.append(_PROSE[key])
        for c in REGISTRY:
            if c.category != key:
                continue
            out.extend(_entry_lines(c.grammar, c.keys, c.help))
        if key == "record":
            out.append("")
            out.append(_rule_line("the legend"))
            out.append(_LEGEND)
    out.append("")
    out.append(
        f"[{_MUTED}]THE BUREAU MAKES NO REPRESENTATIONS REGARDING\n"
        f"THE ACCURACY OF THIS REFERENCE. FORM ACB-99.[/{_MUTED}]"
    )
    return "\n".join(out)


class HelpScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=False),
        Binding("question_mark", "dismiss", "Close", show=False),
        Binding("q", "dismiss", "Close", show=False),
    ]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
        background: #1a1815 60%;
    }
    #help-box {
        width: 58;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        background: #201d18;
        border: round #3a3530;
        border-title-color: #C15F3C;
        overflow-y: auto;
    }
    """

    def compose(self) -> ComposeResult:
        # Rich markup (not Textual Content markup): preserves the space runs
        # that column-align this reference sheet.
        box = Static(Text.from_markup(build_reference()), id="help-box")
        box.border_title = "FORM ACB-99"
        yield box
