"""About overlay — the instrument's papers."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from vagari import __version__

_ABOUT_TEXT = f"""\
[bold #C15F3C]VAGARI[/bold #C15F3C] [#7a756e]{__version__}[/#7a756e]  [#7a756e]— Latin: to wander[/#7a756e]

[#e8e6e3]Chain Custody Instrument[/#e8e6e3]
[#7a756e]Anoikis Cartographic Bureau
Department of Spatial Relations
Ministry of Pantoscopic Observance[/#7a756e]

[#3a3530]─────────────────────────────────────────[/#3a3530]

[#7a756e]A single-pilot wormhole chain mapper.
Local state. No login. No server. The
paste is the truth; the Bureau merely
reconciles.[/#7a756e]

[#3a3530]── papers on file ───────────────────────[/#3a3530]

[#e8e6e3]Interaction model[/#e8e6e3] [#7a756e]after chloroken's
bashmapper (MIT) — the chain is a tree,
three letters address everything.[/#7a756e]

[#e8e6e3]J-space reference[/#e8e6e3] [#7a756e]derived from anoik.is
via the Bureau's spookyspace ingest.[/#7a756e]

[#e8e6e3]Site intelligence[/#e8e6e3] [#7a756e]per the ARCHAEOLOGY and
INHALATION circulars, as codified in
PANTOSCOPE's probe-scan parser.[/#7a756e]

[#e8e6e3]Sibling instruments[/#e8e6e3] [#7a756e]HARUSPEX ·
AUSPEX · RETROSPEX · PANTOSCOPE · PERISCOPE[/#7a756e]

[#e8e6e3]The Ministry[/#e8e6e3] [#C15F3C]observance.app/ministry[/#C15F3C]
[#7a756e]full instrument roster on file[/#7a756e]
[#e8e6e3]Pantoscope[/#e8e6e3] [#C15F3C]observance.app[/#C15F3C]
[#e8e6e3]Periscope[/#e8e6e3] [#C15F3C]periscope.observance.app[/#C15F3C]

[#3a3530]─────────────────────────────────────────[/#3a3530]

[#7a756e]MIT licensed. Not affiliated with CCP
Games. EVE Online is the property of
CCP hf. ACTA PUBLICA · BONUM PUBLICUM.[/#7a756e]\
"""


class AboutScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=False),
        Binding("a", "dismiss", "Close", show=False),
        Binding("q", "dismiss", "Close", show=False),
    ]

    DEFAULT_CSS = """
    AboutScreen {
        align: center middle;
        background: #1a1815 60%;
    }
    #about-box {
        width: 47;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        background: #201d18;
        border: round #3a3530;
        overflow-y: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(Text.from_markup(_ABOUT_TEXT), id="about-box")
