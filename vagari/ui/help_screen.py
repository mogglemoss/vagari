"""Help overlay, Ministry voice."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

_HELP_TEXT = """\
[bold #C15F3C]ANOIKIS CARTOGRAPHIC BUREAU[/bold #C15F3C]  [#7a756e]instrument reference[/#7a756e]

[#3a3530]── how to drive it ──────────────────────[/#3a3530]
  [#e8e6e3]Paste scan telemetry any time the map
  has focus — no mode, no prompt.[/#e8e6e3]
  [#e8e6e3]Bold single keys below act instantly.
  Typing anything else starts a submission
  ([bold]nav qlm[/bold], [bold]htx J105443[/bold], …). [bold]Enter[/bold] files
  it; [bold]Esc[/bold] withdraws it.[/#e8e6e3]
  [#e8e6e3]If a submission begins with an instant
  key's letter ([bold]eol[/bold], [bold]del[/bold], a sig like EAB),
  press [bold]:[/bold] first — [bold]:[/bold] always works.[/#e8e6e3]

[#3a3530]── deposits ─────────────────────────────[/#3a3530]
  [italic]paste[/italic]      deposit scan telemetry (implicit add)
  [bold]lazy[/bold]       arm reconciliation for next deposit
  [bold]sweep[/bold]      strike despawned sigs from record

[#3a3530]── navigation ───────────────────────────[/#3a3530]
  [bold]nav abc[/bold]    proceed through wormhole ABC
  [bold]up[/bold] / [bold]u[/bold]     return toward the root
  [bold]top[/bold] / [bold]g[/bold]    return to the root
  [bold]Enter[/bold]      proceed into selected wormhole

[#3a3530]── the record ───────────────────────────[/#3a3530]
  [bold]abc J105443[/bold]   open ABC to a catalogued system
  [bold]abc H296[/bold]      type wormhole ABC (class, life)
  [bold]abc <words>[/bold]   label a signature
  [bold]here <name>[/bold]   name the current system
  [bold]flag abc[/bold] / [bold]x[/bold] flag · [bold]del abc[/bold] / [bold]d[/bold] strike
  [bold]eol abc[/bold] / [bold]e[/bold]  toggle end-of-life
  [bold]crit abc[/bold] / [bold]m[/bold] cycle mass state
  [bold]zaa = abc[/bold]  refile a placeholder's real sig
  [bold]cull[/bold]       strike holes past book lifetime
  [bold]c[/bold] / [bold]copy[/bold]   chain as text to clipboard

[#3a3530]── the legend ───────────────────────────[/#3a3530]
  [#C15F3C]○[/#C15F3C] wormhole   [#7a756e]▸ combat  ◇ data  ◈ relic[/#7a756e]
  [#7a756e]≈ gas  ▪ ore  · unresolved  ![/#7a756e] flagged

[#3a3530]── views & custody ──────────────────────[/#3a3530]
  [bold]1[/bold]/[bold]2[/bold]/[bold]3[/bold]      full / paths / gas
  [bold]z[/bold] / [bold]Z[/bold]      undo / redo (unbounded)
  [bold]chain <name>[/bold] switch chain of custody
  [bold]recon[/bold]      refresh system activity (ESI)

[#3a3530]── follow-me ────────────────────────────[/#3a3530]
  [#7a756e]jump in-game and ◉ YOU follows via chatlog[/#7a756e]
  [bold]k[/bold] / [bold]k162[/bold]   file an unmapped arrival as K162
  [bold]:[/bold]        focus the submission line
  [bold]?[/bold]        show / close this reference
  [bold]a[/bold]        about — the instrument's papers
  [bold]q[/bold]        quit

[#7a756e]THE BUREAU MAKES NO REPRESENTATIONS REGARDING
THE ACCURACY OF THIS REFERENCE. FORM ACB-99.[/#7a756e]\
"""


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
        width: 56;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        background: #201d18;
        border: round #3a3530;
        overflow-y: auto;
    }
    """

    def compose(self) -> ComposeResult:
        # Rich markup (not Textual Content markup): preserves the space runs
        # that column-align this reference sheet.
        yield Static(Text.from_markup(_HELP_TEXT), id="help-box")
