"""Help overlay, Ministry voice."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

_HELP_TEXT = r"""
[bold #C15F3C]ANOIKIS CARTOGRAPHIC BUREAU[/bold #C15F3C]  [#7a756e]instrument reference[/#7a756e]

[#3a3530]── how to drive it ──────────────────────[/#3a3530]
  [#e8e6e3]Paste scan telemetry any time the map
  has focus — no mode, no prompt.[/#e8e6e3]
  [#e8e6e3]Bold single keys act on the map.
  [bold]Tab[/bold] or [bold]:[/bold] moves to the submission line
  ([bold]nav qlm[/bold], [bold]htx J105443[/bold], …). [bold]Enter[/bold] files
  it; [bold]Esc[/bold] or [bold]Tab[/bold] returns to the map.[/#e8e6e3]

[#3a3530]── deposits ─────────────────────────────[/#3a3530]
  [italic]paste[/italic]      deposit scan telemetry; despawn
             candidates are reported every time
  [bold]s[/bold] / [bold]sweep[/bold]  strike reported despawns

[#3a3530]── navigation ───────────────────────────[/#3a3530]
  [bold]nav abc[/bold]    proceed through wormhole ABC
  [bold]up[/bold] / [bold]u[/bold]     return toward the root
  [bold]top[/bold] / [bold]g[/bold]    return to the root
  [bold]Enter[/bold]      proceed into selected wormhole

[#3a3530]── the record ───────────────────────────[/#3a3530]
  [bold]abc J105443[/bold]   open ABC to a catalogued system
  [bold]abc H296[/bold]      type wormhole ABC (class, life)
  [bold]abc <words>[/bold]   label a signature
  [bold]return abc[/bold]    abc is the way home (pairs with
             the hole its system was entered by)
  [bold]… @system[/bold]    address a sig in a named system;
             otherwise: current first, then unique
  [bold]here <name>[/bold]   name the current system
  [bold]flag abc[/bold] / [bold]x[/bold] flag · [bold]del abc[/bold] / [bold]d[/bold] strike
  [bold]eol abc[/bold] / [bold]e[/bold]  toggle end-of-life
  [bold]crit abc[/bold] / [bold]m[/bold] cycle mass state
  [bold]zaa = abc[/bold]  refile a placeholder's real sig
  [bold]return ina B274[/bold] optional type read on the
             far side; other end wears K162
  [bold]sever abc[/bold]  collapsed hole → far side becomes
             an adrift fragment (kept, not lost)
  [bold]fragment \[name][/bold] file an unattached fragment
  [bold]discard N[/bold]  strike adrift fragment N whole
  [bold]cull[/bold]       strike holes past book lifetime
             (mapped children sever, not vanish)
  [bold]c[/bold] / [bold]copy[/bold]   chain as text to clipboard

[#3a3530]── the legend ───────────────────────────[/#3a3530]
  [#C15F3C]○[/#C15F3C] wormhole   [#7a756e]▸ combat  ◇ data  ◈ relic[/#7a756e]
  [#7a756e]≈ gas  ▪ ore  · unresolved  ![/#7a756e] flagged

[#3a3530]── finding things ───────────────────────[/#3a3530]
  [bold]/query[/bold]     find a system, sig, or label
             (repeat to cycle the matches)
  [bold]intel[/bold]      zKill dossier for this system
  [#7a756e]k-space exits gain sec + region on file
  automatically once named[/#7a756e]

[#3a3530]── the mouse ────────────────────────────[/#3a3530]
  [#e8e6e3]click selects · double-click proceeds
  the dossier panel's [bold]nav eol mass flag
  strike return[/bold] links act on the selection
  → accepts the typed suggestion[/#e8e6e3]

[#3a3530]── views & custody ──────────────────────[/#3a3530]
  [bold]1[/bold]–[bold]5[/bold]      all / paths / sites / gas / combat
  [bold]y[/bold]        cursor to ◉ YOU
  [bold]h[/bold] / [bold]home[/bold]   the route home, door by door
  [bold]copy route[/bold] homeward route to clipboard
  [bold]z[/bold] / [bold]Z[/bold]      undo / redo (unbounded)
  [bold]chain <name>[/bold] switch chain of custody
  [bold]recon[/bold]      refresh system activity (ESI)
  [bold]pilot[/bold]      who is followed · [bold]pilot <name>[/bold] lock
             [bold]pilot off[/bold] → first pilot to jump wins

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
