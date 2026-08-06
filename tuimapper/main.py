"""tuimapper — wormhole chain custody instrument (working title).

ANOIKIS CARTOGRAPHIC BUREAU · Department of Spatial Relations
Ministry of Pantoscopic Observance
"""

from __future__ import annotations

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Input, Static, Tree

from tuimapper.model.store import Store
from tuimapper.session import Session
from tuimapper.ui.chain_tree import ChainTree
from tuimapper.ui.detail_panel import DetailPanel
from tuimapper.ui.help_screen import HelpScreen

BRAND = "ANOIKIS CARTOGRAPHIC BUREAU"


class MapperApp(App):
    TITLE = "TUIMAPPER"
    SUB_TITLE = f"{BRAND} · Chain Custody Instrument · Capsuleer Edition"
    CSS_PATH = "ui/theme.tcss"

    BINDINGS = [
        Binding("question_mark", "show_help", "Reference", show=True),
        Binding("colon", "focus_command", "Submit", show=True),
        Binding("z", "undo", "Undo", show=True),
        Binding("Z", "redo", "Redo", show=False),
        Binding("u", "go_up", "Up", show=False),
        Binding("g", "go_top", "Top", show=False),
        Binding("1", "set_view('full')", "Full", show=False),
        Binding("2", "set_view('paths')", "Paths", show=False),
        Binding("3", "set_view('gas')", "Gas", show=False),
        Binding("e", "sig_cmd('eol')", "EOL", show=False),
        Binding("m", "sig_cmd('crit')", "Mass", show=False),
        Binding("x", "sig_cmd('flag')", "Flag", show=False),
        Binding("d", "sig_cmd('del')", "Strike", show=False),
        Binding("l", "arm_lazy", "Lazy", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self, session: Session | None = None) -> None:
        super().__init__()
        self.session = session or Session.open(Store())

    def compose(self) -> ComposeResult:
        yield Static(id="app-header")
        with Horizontal(id="body"):
            yield ChainTree(self.session, id="chain-tree")
            yield DetailPanel(self.session, id="detail-panel")
        yield Static(
            "The Bureau is ready. Deposit scan telemetry by pasting it.",
            id="status-line",
        )
        yield Input(
            placeholder="submission — e.g.  nav abc · abc J105443 · lazy · ? for reference",
            id="command-bar",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_all()
        self.query_one(ChainTree).focus()

    # -- refresh -------------------------------------------------------------

    def refresh_all(self) -> None:
        tree = self.query_one(ChainTree)
        tree.rebuild()
        self.query_one("#app-header", Static).update(
            f"[bold #C15F3C]{self.TITLE}[/bold #C15F3C] "
            f"[#7a756e]· {BRAND} · chain[/#7a756e] "
            f"[#e8e6e3]{self.session.chain.name}[/#e8e6e3] "
            f"[#7a756e]·[/#7a756e] [#e8e6e3]{self.session.breadcrumb()}[/#e8e6e3]"
            + ("  [bold #d4a017]LAZY ARMED[/bold #d4a017]" if self.session.lazy_armed else "")
        )
        self.session.dirty = False

    def status(self, message: str) -> None:
        self.query_one("#status-line", Static).update(message)

    def _after_engine(self, message: str) -> None:
        self.status(message)
        if self.session.dirty:
            self.refresh_all()

    # -- paste ---------------------------------------------------------------

    def on_paste(self, event: events.Paste) -> None:
        if isinstance(self.focused, Input):
            return  # let the command bar receive pasted text
        self._after_engine(self.session.ingest(event.text))
        event.stop()

    # -- command bar ---------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        self.query_one(ChainTree).focus()
        if not text:
            return
        if text in ("?", "help"):
            self.action_show_help()
            return
        if text.startswith(":"):
            text = text[1:].strip()
        self._after_engine(self.session.execute(text))

    def on_key(self, event: events.Key) -> None:
        if isinstance(self.focused, Input) and event.key == "escape":
            self.query_one(ChainTree).focus()
            event.stop()

    # -- tree selection ------------------------------------------------------

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        self.query_one(DetailPanel).show_node(event.node.data)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if data is None:
            return
        if data[0] == "system":
            path = data[1]
        else:
            _, path, prefix = data
            system = self.session.chain.system_at(path)
            if system.find_connection(prefix) is None:
                return  # selecting a site does nothing; sites are not doors
            path = path + [prefix]
        self._after_engine(self.session.jump(path))

    def _selected_sig(self) -> tuple[list, str] | None:
        node = self.query_one(ChainTree).cursor_node
        if node is None or node.data is None or node.data[0] != "sig":
            return None
        return node.data[1], node.data[2]

    # -- actions -------------------------------------------------------------

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_focus_command(self) -> None:
        self.query_one("#command-bar", Input).focus()

    def action_undo(self) -> None:
        self._after_engine(self.session.undo())

    def action_redo(self) -> None:
        self._after_engine(self.session.redo())

    def action_go_up(self) -> None:
        self._after_engine(self.session.execute("up"))

    def action_go_top(self) -> None:
        self._after_engine(self.session.execute("top"))

    def action_set_view(self, view: str) -> None:
        self._after_engine(self.session.execute(view))

    def action_arm_lazy(self) -> None:
        self._after_engine(self.session.execute("lazy"))
        self.refresh_all()  # show LAZY ARMED in header

    def action_sig_cmd(self, cmd: str) -> None:
        selected = self._selected_sig()
        if selected is None:
            self.status("Select a signature first. The Bureau requires specificity.")
            return
        path, prefix = selected
        if path != self.session.chain.location:
            self.status(
                "Selection lies outside the current system. Proceed there first (Enter)."
            )
            return
        self._after_engine(self.session.execute(f"{cmd} {prefix}"))


def main() -> None:
    MapperApp().run()


if __name__ == "__main__":
    main()
