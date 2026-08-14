"""The instrument reference — generated from the command registry so the
help, the palette, and the suggester can never drift apart."""

from __future__ import annotations

import textwrap

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from vagari.commands import CATEGORIES, REGISTRY

_RUST = "#C15F3C"
_MUTED = "#7a756e"
_TEXT = "#e8e6e3"
_LINE = "#3a3530"

# One layout rules the whole sheet: a bold term column, a muted body
# column, hanging indents on every wrapped line.
_TERM_WIDTH = 18
_BODY_WIDTH = 32
_CONTENT_WIDTH = 2 + _TERM_WIDTH + 1 + _BODY_WIDTH  # 53

# Interaction-model pairs rendered exactly like registry entries, so
# "how to drive it" and the command tables share one look.
_EXTRAS: dict[str, list[tuple[str, str]]] = {
    "drive": [
        ("the map", "bold keys act on it; paste a probe scan whenever it "
                    "has focus — no mode, no prompt"),
        ("Tab · :", "to the submission line; Enter files it; Esc or Tab "
                    "returns"),
        ("→", "accepts the ghost suggestion"),
        ("the mouse", "click selects · double-click proceeds · dossier "
                      "links act on the selection"),
    ],
    "follow": [
        ("chatlogs", "jump in-game and ◉ YOU follows; fleetmates appear "
                     "as ◎ Name"),
    ],
}

_LEGEND = (
    f"  [{_RUST}]○[/{_RUST}] wormhole   [{_MUTED}]▸ combat  ◇ data  ◈ relic[/{_MUTED}]\n"
    f"  [{_MUTED}]≈ gas  ▪ ore  · unresolved  ![/{_MUTED}] flagged"
)

# The quick start. It assumes nothing about where the pilot is or what
# they scan for — the chain grows from wherever the first paste lands.
_PROCEDURE = [
    "paste a probe scan — anywhere, any time; every signature is filed, "
    "sites and gas included",
    "name where you are (here <name>) — or your chatlogs will, the first "
    "time you jump",
    "a first scan's lone wormhole pairs itself as your return",
    "type a hole (xpa Z060) or click a candidate in its dossier",
    "jump — every arrival files itself; the map follows you",
    "scan · paste · repeat — home retraces the chain to where you began",
]

_FOOTER = (
    "THE BUREAU MAKES NO REPRESENTATIONS REGARDING THE ACCURACY OF THIS "
    "REFERENCE. FORM ACB-99."
)


def _rule_line(title: str) -> str:
    bar = "─" * max(3, _CONTENT_WIDTH - len(title) - 4)
    return (
        f"[{_LINE}]──[/{_LINE}] [bold {_MUTED}]{title}[/bold {_MUTED}] "
        f"[{_LINE}]{bar}[/{_LINE}]"
    )


def _escape(text: str) -> str:
    """Literal brackets in grammar ('fragment [name]') must not be tags."""
    return text.replace("[", "\\[")


def _entry_lines(term: str, keys: str, body: str) -> list[str]:
    head = term
    if keys and keys != term:
        head += f" · {keys}"
    wrapped = textwrap.wrap(body, _BODY_WIDTH) or [""]
    pad = " " * (_TERM_WIDTH + 3)
    lines = []
    if len(head) <= _TERM_WIDTH:
        lines.append(
            f"  [bold]{_escape(head):<{_TERM_WIDTH + head.count('[')}}[/bold] "
            f"[{_MUTED}]{_escape(wrapped[0])}[/{_MUTED}]"
        )
        rest = wrapped[1:]
    else:
        lines.append(f"  [bold]{_escape(head)}[/bold]")
        rest = wrapped
    for w in rest:
        lines.append(f"{pad}[{_MUTED}]{_escape(w)}[/{_MUTED}]")
    return lines


def _procedure_lines() -> list[str]:
    lines = []
    for n, step in enumerate(_PROCEDURE, 1):
        wrapped = textwrap.wrap(step, _CONTENT_WIDTH - 5)
        lines.append(
            f"  [{_RUST}]{n}[/{_RUST}]  "
            f"[{_TEXT}]{_escape(wrapped[0])}[/{_TEXT}]"
        )
        for w in wrapped[1:]:
            lines.append(f"     [{_TEXT}]{_escape(w)}[/{_TEXT}]")
    return lines


def build_reference() -> str:
    out = [
        f"[bold {_RUST}]ANOIKIS CARTOGRAPHIC BUREAU[/bold {_RUST}]",
        f"[{_MUTED}]Department of Spatial Relations · instrument "
        f"reference[/{_MUTED}]",
        "",
        _rule_line("field procedure"),
    ]
    out.extend(_procedure_lines())
    for key, title in CATEGORIES:
        out.append("")
        out.append(_rule_line(title))
        for term, body in _EXTRAS.get(key, ()):
            out.extend(_entry_lines(term, "", body))
        for c in REGISTRY:
            if c.category != key:
                continue
            out.extend(_entry_lines(c.grammar, c.keys, c.help))
        if key == "record":
            out.append("")
            out.append(_rule_line("the legend"))
            out.append(_LEGEND)
    out.append("")
    for w in textwrap.wrap(_FOOTER, _CONTENT_WIDTH - 2):
        out.append(f"  [{_MUTED}]{w}[/{_MUTED}]")
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
        width: 60;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        background: #201d18;
        border: round #3a3530;
        border-title-color: #C15F3C;
        scrollbar-size-vertical: 1;
        scrollbar-color: #3a3530;
        scrollbar-color-hover: #C15F3C;
        scrollbar-color-active: #C15F3C;
        scrollbar-background: #201d18;
    }
    """

    def compose(self) -> ComposeResult:
        # Rich markup (not Textual Content markup): preserves the space runs
        # that column-align this reference sheet.
        box = VerticalScroll(
            Static(Text.from_markup(build_reference())), id="help-box"
        )
        box.border_title = "FORM ACB-99"
        yield box

    def on_mount(self) -> None:
        # Focused scroll container: arrows and PgUp/PgDn page the sheet.
        self.query_one("#help-box").focus()
