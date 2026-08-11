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
from vagari.ui.palette import ChainSearchProvider
from vagari.ui.suggest import BureauSuggester
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
    COMMANDS = App.COMMANDS | {ChainSearchProvider}
    SUB_TITLE = f"{BRAND} · Chain Custody Instrument · Capsuleer Edition"
    CSS_PATH = "ui/theme.tcss"

    BINDINGS = [
        Binding("question_mark", "show_help", "Reference", show=True),
        Binding("colon", "focus_command", "Submit", show=True),
        Binding("tab", "toggle_focus", "Map⇄Submit", show=True, priority=True),
        Binding("z", "undo", "Undo", show=True),
        Binding("Z", "redo", "Redo", show=False),
        Binding("u", "go_up", "Up", show=False),
        Binding("g", "go_top", "Top", show=False),
        Binding("1", "set_view('full')", "Full", show=False),
        Binding("2", "set_view('paths')", "Paths", show=False),
        Binding("3", "set_view('sites')", "Sites", show=False),
        Binding("4", "set_view('gas')", "Gas", show=False),
        Binding("5", "set_view('combat')", "Combat", show=False),
        Binding("e", "sig_cmd('eol')", "EOL", show=False),
        Binding("m", "sig_cmd('crit')", "Mass", show=False),
        Binding("x", "sig_cmd('flag')", "Flag", show=False),
        Binding("d", "sig_cmd('del')", "Strike", show=False),
        Binding("s", "sweep", "Sweep", show=True),
        Binding("y", "snap_to_you", "You", show=False),
        Binding("h", "show_homeward", "Homeward", show=False),
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
        """The palette is generated from the command registry — same truth
        as the reference screen and the suggester. Textual's defaults are
        replaced (theme switching would undermine the Ministry)."""
        from vagari.commands import REGISTRY

        special = {
            "sweep": self.action_sweep,
            "cull": lambda: self._after_engine(self.session.execute("cull")),
            "recon": lambda: self.run_worker(
                self._refresh_activity(), exclusive=True, group="recon"
            ),
            "request_intel": self._request_intel,
        }
        for c in REGISTRY:
            if not c.palette:
                continue
            fn = special.get(c.action) or getattr(
                self, f"action_{c.action}", None
            )
            if fn is None:
                continue
            desc = c.help + (f"  ·  key: {c.keys}" if c.keys else "")
            yield SystemCommand(c.palette, desc, fn)
        yield SystemCommand("Redo", "reinstate one revision  ·  key: Z",
                            self.action_redo)
        yield SystemCommand("Copy route", "homeward route to the clipboard",
                            self.action_copy_route)
        for view, blurb in [
            ("full", "all signatures"), ("paths", "wormholes only"),
            ("sites", "wormholes, relic/data/ghost"),
            ("gas", "wormholes and gas"), ("combat", "wormholes and combat"),
        ]:
            yield SystemCommand(
                f"View: {view}", blurb,
                lambda v=view: self.action_set_view(v),
            )

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
            placeholder="submission — e.g.  nav abc · abc J105443 · sweep · ? for reference",
            id="command-bar",
            suggester=BureauSuggester(self.session),
        )
        yield Footer()

    def on_mount(self) -> None:
        # Without this, focusing the bar selects its contents and the next
        # keystroke replaces the fzf-seeded character.
        self.query_one("#command-bar", Input).select_on_focus = False
        self.refresh_all()
        hint = self.session.orientation_hint()
        if hint:
            self.status(hint)
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
        alerts = self.session.sample_activity()
        if alerts:
            self.query_one(VagariHeader).flare()
            message = "WATCHTOWER: activity in " + "; ".join(alerts)
            self.status(message + ". The Bureau is merely noting. Loudly.")
            # Danger is the one thing that earns a toast and a pulse.
            self.notify(message, title="WATCHTOWER", severity="warning",
                        timeout=8)
            tree = self.query_one(ChainTree)
            tree.add_class("alerting")
            self.set_timer(2.0, lambda: tree.remove_class("alerting"))
        node = self.query_one(ChainTree).cursor_node
        self.query_one(DetailPanel).show_node(node.data if node else None)
        self.status(f"Reconnaissance filed: activity for {len(activity)} systems.")

    # -- refresh -------------------------------------------------------------

    def refresh_all(self) -> None:
        tree = self.query_one(ChainTree)
        tree.rebuild()
        view = self.session.view
        tree.border_title = (
            "THE CHAIN" if view == "full" else f"THE CHAIN · {view.upper()} VIEW"
        )
        self.query_one(DetailPanel).border_title = "DOSSIER"

        self.query_one(VagariHeader).update_state(
            self.session.chain.name,
            self.session.breadcrumb(),
            pending_arrival=(
                self.session.pending_arrival[0]
                if self.session.pending_arrival
                else None
            ),
            pilot=self.session.pilot_lock,
            follow_active=getattr(self, "_follow_active", False),
            despawned=(
                self.session.last_report.despawned
                if self.session.last_report
                else []
            ),
        )
        self.session.dirty = False

    def status(self, message: str) -> None:
        self.query_one("#status-line", Static).update(message)

    def _after_engine(self, message: str) -> None:
        hint = self.session.orientation_hint()
        if hint:
            message = f"{message}  ·  {hint}"
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
        if event.input.id != "command-bar":
            return  # dossier forms handle their own submissions
        text = event.value.strip()
        event.input.value = ""
        self.query_one(ChainTree).focus()
        if text:
            self.submit_text(text)

    def submit_text(self, text: str) -> None:
        """The front door for filings — the command bar, dossier action
        links, and dossier forms all arrive here, identically."""
        if text in ("?", "help"):
            self.action_show_help()
            return
        if text in ("copy route", "copy home", "route copy"):
            self.action_copy_route()
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

    def on_key(self, event: events.Key) -> None:
        if isinstance(self.focused, Input) and event.key == "escape":
            self.query_one(ChainTree).focus()
            event.stop()

    def action_toggle_focus(self) -> None:
        """Tab hops between the map and the submission line."""
        if isinstance(self.focused, Input):
            self.query_one(ChainTree).focus()
        else:
            self.query_one("#command-bar", Input).focus()

    # -- tree selection ------------------------------------------------------

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        panels = self.query(DetailPanel)
        if panels:  # guard: highlight events can fire during teardown
            panels.first().show_node(event.node.data)

    def on_data_table_row_selected(self, event) -> None:
        """Dossier signature table: clicking a row selects it on the map."""
        panel = self.query_one(DetailPanel)
        prefix = event.row_key.value if event.row_key else None
        if prefix:
            self.query_one(ChainTree).move_to_data(
                ("sig", list(panel.table_path), prefix)
            )

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        tree = self.query_one(ChainTree)
        if tree.suppress_click_nav:
            tree.suppress_click_nav = False
            return  # single click inspects; double-click or Enter proceeds
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
        from vagari.enrichers.zkill import fetch_system_intel, human_isk

        intel = await fetch_system_intel(system_id)
        if intel is None:
            self.status("zKillboard unavailable. The Bureau does not speculate offline.")
            return
        self.session.zkill_stats[system_id] = intel
        node = self.query_one(ChainTree).cursor_node
        self.query_one(DetailPanel).show_node(node.data if node else None)
        bits = []
        if intel.stats:
            bits.append(
                f"{intel.stats.ships_destroyed:,} ships · "
                f"{human_isk(intel.stats.isk_destroyed)} ISK all-time"
            )
        if intel.last_kill and intel.last_kill.time:
            from vagari.ui.chain_tree import age_text

            bits.append(f"last kill {age_text(intel.last_kill.time)} ago")
        self.status(f"Intel filed for {name}: " + " · ".join(bits) + ".")

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

    def action_copy_route(self) -> None:
        self.copy_to_clipboard(self.session.homeward())
        self.status("Route copied to clipboard. Distribute to the lost.")

    def action_show_homeward(self) -> None:
        self.status(self.session.homeward())

    def jump_to_data(self, data: tuple) -> None:
        """Palette hit: move the map cursor to a system or signature."""
        self.query_one(ChainTree).move_to_data(data)

    def action_run_cmd(self, text: str) -> None:
        """Dossier link: any filing the submission line accepts."""
        self.submit_text(text)

    def _qualifier(self, path: list) -> str:
        """`@system` suffix so a filing lands on the selected sig even when
        the cursor is parked far from ◉ YOU."""
        name = self.session.chain.system_at(path).name
        if name and not name.startswith("?"):
            return f" @{name}"
        return ""

    def action_set_selected_type(self, code: str) -> None:
        """Dossier link: type the selected wormhole with a candidate code."""
        sel = self._selected_sig()
        if sel is None:
            self.status("Select a signature first. The Bureau requires specificity.")
            return
        path, prefix = sel
        self._after_engine(
            self.session.execute(f"{prefix} {code}{self._qualifier(path)}")
        )

    def action_select_at(self, spec: str, prefix: str) -> None:
        """Dossier link: move the map cursor to a signature row."""
        parts = spec.split("/")
        path = [int(parts[0])] + parts[1:]
        self.query_one(ChainTree).move_to_data(("sig", path, prefix))

    def action_snap_to_you(self) -> None:
        tree = self.query_one(ChainTree)
        if tree.move_to_data(("system", list(self.session.chain.location))):
            self.status(f"Cursor on ◉ YOU — {self.session.chain.current().name}.")

    def action_nav_selected(self) -> None:
        """Detail-panel action link: proceed to the selection."""
        node = self.query_one(ChainTree).cursor_node
        if node is not None and node.data is not None:
            self.query_one(ChainTree).suppress_click_nav = False
            self.on_tree_node_selected(Tree.NodeSelected(node))

    def action_return_selected(self) -> None:
        """Detail-panel action link: file selection as the return side."""
        sel = self._selected_sig()
        if sel is not None:
            _path, prefix = sel
            self._after_engine(self.session.execute(f"return {prefix}"))

    def action_sweep(self) -> None:
        self._after_engine(self.session.execute("sweep"))

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
        # `d` on a fragment header discards the fragment itself.
        if cmd == "del":
            node = self.query_one(ChainTree).cursor_node
            if (
                node is not None
                and node.data is not None
                and node.data[0] == "system"
                and len(node.data[1]) == 1
            ):
                ri = node.data[1][0]
                self._after_engine(self.session.execute(f"discard {ri + 1}"))
                return
        selected = self._selected_sig()
        if selected is None:
            self.status("Select a signature first. The Bureau requires specificity.")
            return
        path, prefix = selected
        qualifier = (
            "" if path == self.session.chain.location else self._qualifier(path)
        )
        self._after_engine(self.session.execute(f"{cmd} {prefix}{qualifier}"))


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
