"""vagari — wormhole chain custody instrument (working title).

ANOIKIS CARTOGRAPHIC BUREAU · Department of Spatial Relations
Ministry of Pantoscopic Observance
"""

from __future__ import annotations

from textual import events
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Input, Static, Tree

from vagari.enrichers.activity import fetch_system_kills
from vagari.followme.logtail import LocalEvent, detect_chatlog_dir, tail_local_files
from vagari.model.store import Store
from vagari.session import Session
from vagari.ui.about_screen import AboutScreen
from vagari.ui.chain_tree import ChainTree
from vagari.ui.detail_panel import DetailPanel
from vagari.ui.help_screen import HelpScreen
from vagari.ui.widgets import VagariHeader

# Printed to the terminal after the TUI closes. The Bureau signs off.
FAREWELLS = [
    "The Bureau notes your departure. The chain remains on file.",
    "Your whereabouts are now a matter of speculation. The record is not.",
    "VAGARI has stopped following you. Someone else may not have.",
    "The map is saved. The territory was never the Bureau's responsibility.",
    "Filed under: departed. The Bureau wishes you a boring transit.",
    "Fly safe. Failing that, fly documented.",
    "The instrument rests. The holes do not.",
    "Custody of the chain reverts to memory. The Bureau recommends against this.",
    "Your signatures will despawn. The paperwork is forever.",
    "The Bureau has never lost a pilot. It has lost several records of pilots.",
    "Departure noted at [no timestamp]. Clocks are a k-space affectation.",
    "Wander accordingly.",
]

BRAND = "ANOIKIS CARTOGRAPHIC BUREAU"


class MapperApp(App):
    TITLE = "VAGARI"
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
        Binding("c", "copy_chain", "Copy", show=True),
        Binding("k", "file_k162", "File K162", show=False),
        Binding("a", "show_about", "About", show=False),
        Binding("slash", "start_search", "Find", show=False),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(
        self,
        session: Session | None = None,
        *,
        recon: bool = True,
        follow: bool = True,
    ) -> None:
        super().__init__()
        self.session = session or Session.open(Store())
        self.recon_enabled = recon    # tests disable the network fetch
        self.follow_enabled = follow  # tests disable the chatlog tailer
        self._search: tuple[str, int] | None = None  # (query, match index)

    def get_system_commands(self, screen):
        """Curated Bureau commands for the palette (Ctrl+P) — replaces
        Textual's defaults (theme switching would undermine the Ministry)."""
        yield SystemCommand(
            "Reference", "Show the instrument reference (?)", self.action_show_help
        )
        yield SystemCommand(
            "Arm lazy reconciliation",
            "Next deposit reports despawned signatures",
            self.action_arm_lazy,
        )
        yield SystemCommand(
            "Sweep despawned",
            "Strike reported despawns from the record",
            lambda: self._after_engine(self.session.execute("sweep")),
        )
        yield SystemCommand(
            "Recon: refresh activity",
            "One ESI request; last-hour kills per system",
            lambda: self.run_worker(
                self._refresh_activity(), exclusive=True, group="recon"
            ),
        )
        yield SystemCommand(
            "File K162", "File a pending unmapped arrival", self.action_file_k162
        )
        yield SystemCommand("Undo", "Revert one revision", self.action_undo)
        yield SystemCommand("Redo", "Reinstate one revision", self.action_redo)
        yield SystemCommand(
            "View: full", "All signatures", lambda: self.action_set_view("full")
        )
        yield SystemCommand(
            "View: paths", "Wormholes only", lambda: self.action_set_view("paths")
        )
        yield SystemCommand(
            "View: gas", "Wormholes and gas", lambda: self.action_set_view("gas")
        )
        yield SystemCommand(
            "Return to root", "Move ◉ YOU to the top of the chain", self.action_go_top
        )
        yield SystemCommand(
            "Copy chain", "Plain-text tree to the clipboard", self.action_copy_chain
        )
        yield SystemCommand(
            "Find", "Search systems, sigs, and labels", self.action_start_search
        )
        yield SystemCommand(
            "Intel: zKill dossier", "Killboard stats for the current system",
            self._request_intel,
        )
        yield SystemCommand(
            "Cull expired", "Strike holes past their book lifetime",
            lambda: self._after_engine(self.session.execute("cull")),
        )
        yield SystemCommand(
            "About", "The instrument's papers", self.action_show_about
        )
        yield SystemCommand("Quit", "Close the instrument", self.action_quit)

    def compose(self) -> ComposeResult:
        yield VagariHeader(id="app-header")
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
        # Without this, focusing the bar selects its contents and the next
        # keystroke replaces the fzf-seeded character.
        self.query_one("#command-bar", Input).select_on_focus = False
        self.refresh_all()
        self.query_one(ChainTree).focus()
        if self.recon_enabled:
            self.run_worker(self._refresh_activity(), exclusive=True, group="recon")
        if self.follow_enabled:
            chatlog_dir = detect_chatlog_dir()
            if chatlog_dir is None:
                self.status(
                    "Chatlogs not found — follow-me disabled. "
                    "Set VAGARI_LOG_DIR to your EVE Chatlogs directory, and "
                    "ensure 'Log chat to file' is on in EVE's settings."
                )
            else:
                import os

                # Env overrides for this run only; otherwise the persisted
                # lock (loaded in Session.open) stands.
                env_pilot = os.environ.get("VAGARI_PILOT")
                if env_pilot:
                    self.session.pilot_lock = env_pilot
                who = self.session.pilot_lock or "first pilot to jump"
                self.status(f"Monitoring {chatlog_dir.name} — following {who}.")
                self._follow_active = True
                self.run_worker(
                    tail_local_files(chatlog_dir, self._on_local_event),
                    exclusive=True,
                    group="follow",
                )
                self.refresh_all()  # surface the NOT FOLLOWING hint immediately
        # Ages and lifetime countdowns tick; cursor position is preserved.
        self.set_interval(60, self._tick)
        if self.recon_enabled:
            # Auto-recon: refresh activity and record a trend sample.
            self.set_interval(600, self._auto_recon)

    def _auto_recon(self) -> None:
        self.run_worker(self._refresh_activity(), exclusive=True, group="recon")

    async def _on_local_event(self, event: LocalEvent) -> None:
        message = self.session.follow_event(event.pilot, event.system, event.initial)
        if message is not None:
            self._after_engine(message)

    def _tick(self) -> None:
        if not isinstance(self.focused, Input):
            self.refresh_all()

    async def _refresh_activity(self) -> None:
        activity = await fetch_system_kills()
        if activity is None:
            self.session.activity_fetched = False
            self.status("Reconnaissance unavailable. The Bureau does not speculate offline.")
            return
        self.session.activity = activity
        self.session.activity_fetched = True
        self.session.sample_activity()
        node = self.query_one(ChainTree).cursor_node
        self.query_one(DetailPanel).show_node(node.data if node else None)
        self.status(f"Reconnaissance filed: activity for {len(activity)} systems.")

    # -- refresh -------------------------------------------------------------

    def refresh_all(self) -> None:
        tree = self.query_one(ChainTree)
        tree.rebuild()
        self.query_one(VagariHeader).update_state(
            self.session.chain.name,
            self.session.breadcrumb(),
            self.session.lazy_armed,
            pending_arrival=(
                self.session.pending_arrival[0]
                if self.session.pending_arrival
                else None
            ),
            pilot=self.session.pilot_lock,
            follow_active=getattr(self, "_follow_active", False),
        )
        self.session.dirty = False

    def status(self, message: str) -> None:
        self.query_one("#status-line", Static).update(message)

    def _after_engine(self, message: str) -> None:
        self.status(message)
        if self.session.dirty:
            self.query_one(VagariHeader).flare()
            self.refresh_all()
            if self.recon_enabled and self.session.unresolved_kspace_names():
                self.run_worker(self._resolve_kspace(), exclusive=True, group="kspace")

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
        if text == "recon":
            self.status("Reconnaissance dispatched…")
            self.run_worker(self._refresh_activity(), exclusive=True, group="recon")
            return
        if text == "intel":
            self._request_intel()
            return
        if text.startswith("/") or text.lower().startswith("find "):
            query = text[1:] if text.startswith("/") else text[5:]
            self._run_search(query.strip())
            return
        if text.startswith(":"):
            text = text[1:].strip()
        self._after_engine(self.session.execute(text))

    # Keys that act instantly when the map has focus; any other letter or
    # digit starts a submission fzf-style. Submissions that begin with one
    # of these letters need the explicit `:` first.
    _INSTANT_KEYS = set("123acdegklmquxzZ?")

    def on_key(self, event: events.Key) -> None:
        if isinstance(self.focused, Input):
            if event.key == "escape":
                self.query_one(ChainTree).focus()
                event.stop()
            return
        ch = event.character
        if (
            ch
            and ch.isalnum()
            and len(event.key) == 1  # plain keypress, no ctrl/meta chords
            and ch not in self._INSTANT_KEYS
        ):
            bar = self.query_one("#command-bar", Input)
            bar.focus()
            bar.value = ch
            bar.cursor_position = len(bar.value)
            event.stop()
            event.prevent_default()

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

    def action_show_about(self) -> None:
        self.push_screen(AboutScreen())

    def action_start_search(self) -> None:
        bar = self.query_one("#command-bar", Input)
        bar.focus()
        bar.value = "/"
        bar.cursor_position = 1

    def _run_search(self, query: str) -> None:
        if not query:
            self.status("Find what? `/query` searches names, prefixes, labels.")
            return
        matches = self.session.find_matches(query)
        if not matches:
            self._search = None
            self.status(f"No filings match {query!r}.")
            return
        if self._search and self._search[0] == query:
            index = (self._search[1] + 1) % len(matches)
        else:
            index = 0
        self._search = (query, index)
        tree = self.query_one(ChainTree)
        tree._restore_cursor(matches[index])
        tree.focus()
        self.query_one(DetailPanel).show_node(matches[index])
        again = " — `/` and Enter again for the next" if len(matches) > 1 else ""
        self.status(f"Match {index + 1}/{len(matches)} for {query!r}{again}.")

    def _request_intel(self) -> None:
        from vagari.parsers.catalog import lookup_system

        current = self.session.chain.current()
        info = lookup_system(current.name)
        kinfo = self.session.kspace.get(current.name)
        system_id = info.system_id if info else (kinfo.system_id if kinfo else None)
        if system_id is None:
            self.status(f"No system id on file for {current.name} — name it first.")
            return
        self.status(f"Requesting killboard intel for {current.name}…")
        self.run_worker(self._fetch_intel(current.name, system_id), group="intel")

    async def _fetch_intel(self, name: str, system_id: int) -> None:
        from vagari.enrichers.zkill import fetch_system_stats

        stats = await fetch_system_stats(system_id)
        if stats is None:
            self.status("zKillboard unavailable. The Bureau does not speculate offline.")
            return
        self.session.zkill_stats[system_id] = stats
        node = self.query_one(ChainTree).cursor_node
        self.query_one(DetailPanel).show_node(node.data if node else None)
        self.status(
            f"Intel filed for {name}: {stats.ships_destroyed:,} ships destroyed "
            f"all-time · {stats.active_characters} recently active hunters."
        )

    async def _resolve_kspace(self) -> None:
        from vagari.enrichers.kspace import resolve_systems

        names = self.session.unresolved_kspace_names()
        if not names:
            return
        resolved = await resolve_systems(names)
        if resolved:
            self.session.kspace.update(resolved)
            self.refresh_all()

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

    def action_file_k162(self) -> None:
        self._after_engine(self.session.file_k162())

    def action_copy_chain(self) -> None:
        from vagari.export import export_text

        text = export_text(self.session.chain, self.session.view)
        self.copy_to_clipboard(text)
        self.status(
            f"Chain of custody copied ({len(text.splitlines())} lines). "
            "Distribute responsibly."
        )

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
    import sys

    if "--version" in sys.argv:
        # Also exercises the bundled data — a packaging self-test.
        from vagari import __version__
        from vagari.parsers.catalog import load_systems, load_wormhole_types

        print(
            f"VAGARI {__version__} · Anoikis Cartographic Bureau · "
            f"{len(load_systems())} systems · {len(load_wormhole_types())} wormhole types"
        )
        return
    MapperApp().run()
    import random

    print(random.choice(FAREWELLS))


if __name__ == "__main__":
    main()
