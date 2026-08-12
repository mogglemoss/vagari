"""Mouse/keyboard interaction batch: click semantics, snap-to-YOU,
action row, typeahead, candidate types, five views."""

import pytest
from textual.widgets import Static, Tree

from tests.test_app import make_app, paste, tree_text
from vagari.ui.chain_tree import ChainTree
from vagari.ui.detail_panel import DetailPanel


@pytest.mark.asyncio
async def test_single_click_selects_double_click_navigates(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        await pilot.press("colon")
        await pilot.press(*"qlm J154535")
        await pilot.press("enter")
        await pilot.pause()
        tree = app.query_one(ChainTree)

        # Simulate a single click on the wormhole node: select only.
        tree.suppress_click_nav = True
        node = tree.root.children[0].children[-1]  # QLM sig node
        tree.move_cursor(node)
        app.on_tree_node_selected(Tree.NodeSelected(node))
        await pilot.pause()
        assert app.session.chain.location == [0]  # did NOT navigate

        # Enter (no click flag) navigates.
        app.on_tree_node_selected(Tree.NodeSelected(node))
        await pilot.pause()
        assert app.session.chain.location == [0, "QLM"]


@pytest.mark.asyncio
async def test_snap_to_you(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        tree = app.query_one(ChainTree)
        tree.move_cursor(tree.root.children[0].children[0])  # wander off
        assert tree.cursor_node.data != ("system", [0])
        await pilot.press("y")
        await pilot.pause()
        assert tree.cursor_node.data == ("system", [0])


@pytest.mark.asyncio
async def test_action_row_present_and_working(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        panel = app.query_one(DetailPanel)
        panel.show_node(("sig", [0], "FIY"))
        text = str(panel.content)
        assert "@click=app.sig_cmd('eol')" in text
        assert "strike" in text and "flag" in text
        # A site (no connection) offers `return`, not `nav`.
        assert "return_selected" in text and "nav_selected" not in text

        # The linked action operates on the tree selection.
        tree = app.query_one(ChainTree)
        for node in tree.root.children[0].children:
            if node.data == ("sig", [0], "FIY"):
                tree.move_cursor(node)
        app.action_sig_cmd("flag")
        await pilot.pause()
        assert app.session.chain.root.find_sig("FIY").flagged


@pytest.mark.asyncio
async def test_suggester_completions(tmp_path):
    from vagari.ui.suggest import BureauSuggester

    app = make_app(tmp_path)
    s = BureauSuggester(app.session)
    assert await s.get_suggestion("sw") == "sweep"
    assert await s.get_suggestion("htx H2") == "htx H296"
    app.session.known_pilots["Cormorant Fell"] = "Vard"
    # Ghost text keeps the typed casing; pilot resolution is case-insensitive.
    assert await s.get_suggestion("pilot corm") == "pilot cormorant Fell"
    assert await s.get_suggestion("nav ") is None


@pytest.mark.asyncio
async def test_candidate_types_for_untyped_hole(tmp_path):
    app = make_app(tmp_path)  # root J105443, a C1
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        panel = app.query_one(DetailPanel)
        panel.show_node(("sig", [0], "QLM"))  # wormhole, never typed
        text = str(panel.content)
        assert "PLAUSIBLE DESIGNATIONS" in text
        assert "static" in text  # the system's static is marked
        assert "K162" in text and "inbound" in text  # the eternal candidate


@pytest.mark.asyncio
async def test_five_views(tmp_path):
    """Themed views: structural (opened) wormholes stay, unopened ones hide."""
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        # Open QLM so it becomes structure; add an unopened hole too.
        app.session.execute("qlm J154535")
        app.session.ingest(
            "UNO-001\tCosmic Signature\tWormhole\t\t40.0%\t1 AU"
        )
        app.refresh_all()

        await pilot.press("3")  # sites: relic/data only, plus structure
        await pilot.pause()
        text = tree_text(app.query_one(ChainTree))
        assert "FIY" in text and "VMX" not in text
        assert "QLM" in text        # opened → structural, always shown
        assert "UNO" not in text    # unopened wormhole → hidden in themed views

        await pilot.press("4")  # gas
        await pilot.pause()
        text = tree_text(app.query_one(ChainTree))
        assert "VMX" in text and "FIY" not in text and "UNO" not in text

        await pilot.press("2")  # paths: ALL wormholes, opened or not
        await pilot.pause()
        text = tree_text(app.query_one(ChainTree))
        assert "QLM" in text and "UNO" in text and "FIY" not in text

        # The view is announced in the pane title.
        assert "PATHS VIEW" in str(app.query_one(ChainTree).border_title)


@pytest.mark.asyncio
async def test_collapse_state_survives_refresh(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        app.session.execute("qlm J154535")
        app.refresh_all()
        await pilot.pause()
        tree = app.query_one(ChainTree)
        # Collapse the QLM branch, then force a refresh (the 60s tick path).
        assert tree.move_to_data(("sig", [0], "QLM"))
        qlm_node = tree.cursor_node
        qlm_node.collapse()
        assert not qlm_node.is_expanded
        app.refresh_all()
        await pilot.pause()
        assert tree.move_to_data(("sig", [0], "QLM"))
        assert not tree.cursor_node.is_expanded  # collapse survived


@pytest.mark.asyncio
async def test_candidate_types_clickable_and_set_type(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        panel = app.query_one(DetailPanel)
        panel.show_node(("sig", [0], "QLM"))
        assert "@click=app.set_selected_type(" in str(panel.content)

        tree = app.query_one(ChainTree)
        assert tree.move_to_data(("sig", [0], "QLM"))
        app.action_set_selected_type("Z060")  # J105443's static
        await pilot.pause()
        conn = app.session.chain.root.find_connection("QLM")
        assert conn is not None and conn.wh_type == "Z060"


@pytest.mark.asyncio
async def test_dossier_sig_table_selects(tmp_path):
    from textual.widgets import DataTable

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        panel = app.query_one(DetailPanel)
        panel.show_node(("system", [0]))
        await pilot.pause()
        table = panel.query_one("#dossier-sigs", DataTable)
        assert table.display and table.row_count == 4

        cursor_before = app.query_one(ChainTree).cursor_node
        table.move_cursor(row=2)  # FIY
        table.action_select_cursor()
        await pilot.pause()
        # Drills the DOSSIER into the row; the map cursor stays put.
        assert panel._showing == ("sig", [0], "FIY")
        assert "FIY" in str(panel.content)
        assert app.query_one(ChainTree).cursor_node is cursor_before


@pytest.mark.asyncio
async def test_palette_chain_search_jumps(tmp_path):
    from vagari.ui.palette import ChainSearchProvider

    app = make_app(tmp_path)
    assert ChainSearchProvider in app.COMMANDS
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        app.session.execute("qlm J154535")
        app.refresh_all()
        app.jump_to_data(("system", [0, "QLM"]))
        await pilot.pause()
        assert app.query_one(ChainTree).cursor_node.data == ("system", [0, "QLM"])


@pytest.mark.asyncio
async def test_dossier_form_types_hole(tmp_path):
    """The dossier's filing field: type a code by hand, even a rare one."""
    from textual.widgets import Input

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        panel = app.query_one(DetailPanel)
        panel.show_node(("sig", [0], "QLM"))
        await pilot.pause()
        form = panel.query_one("#dossier-form", Input)
        assert form.display
        assert "type" in form.placeholder
        form.focus()
        await pilot.pause()
        form.value = "H296"  # a wanderer — deliberately off the short list
        await pilot.press("enter")
        await pilot.pause()
        conn = app.session.chain.root.find_connection("QLM")
        assert conn is not None and conn.wh_type == "H296"


@pytest.mark.asyncio
async def test_dossier_form_labels_sig(tmp_path):
    from textual.widgets import Input

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        panel = app.query_one(DetailPanel)
        panel.show_node(("sig", [0], "FIY"))
        await pilot.pause()
        form = panel.query_one("#dossier-form", Input)
        assert form.display
        form.focus()
        await pilot.pause()
        form.value = "pristine, save for last"
        await pilot.press("enter")
        await pilot.pause()
        sig = app.session.chain.root.find_sig("FIY")
        assert sig.label == "pristine, save for last"


@pytest.mark.asyncio
async def test_system_dossier_actions_and_here_form(tmp_path):
    from textual.widgets import Input

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        panel = app.query_one(DetailPanel)
        panel.show_node(("system", [0]))  # ◉ YOU
        await pilot.pause()
        text = str(panel.content)
        assert "@click=app.run_cmd('recon')" in text
        assert "@click=app.run_cmd('intel')" in text
        form = panel.query_one("#dossier-form", Input)
        assert form.display and form.placeholder.startswith("here")

        # A non-current system offers nav instead, and no naming form.
        app.session.execute("qlm J154535")
        app.refresh_all()
        panel.show_node(("sig", [0], "QLM"))
        await pilot.pause()
        panel.show_node(("system", [0, "QLM"]))
        await pilot.pause()
        text = str(panel.content)
        assert "@click=app.nav_selected" in text
        assert "strike J154535" in text
        assert not panel.query_one("#dossier-form", Input).display


@pytest.mark.asyncio
async def test_sig_cmd_qualifies_remote_selection(tmp_path):
    """Action links work from anywhere — the filing is @-qualified, not
    refused, when the cursor sits outside the current system."""
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        app.session.execute("qlm J154535")
        app.session.execute("nav QLM")  # ◉ YOU moves off the root
        app.refresh_all()
        await pilot.pause()
        tree = app.query_one(ChainTree)
        assert tree.move_to_data(("sig", [0], "FIY"))  # back in the root
        await pilot.pause()  # highlight lands in the dossier
        app.action_sig_cmd("flag")
        await pilot.pause()
        assert app.session.chain.root.find_sig("FIY").flagged


@pytest.mark.asyncio
async def test_killboard_section_always_present(tmp_path):
    """The dossier never stays mute on killboard matters: stats, a quiet
    verdict, or an inquiry line — always something."""
    from datetime import timedelta

    from vagari.enrichers.zkill import LastKill, SystemIntel
    from vagari.model.chain import utcnow
    from vagari.parsers.catalog import lookup_system

    app = make_app(tmp_path)  # recon disabled: no auto-inquiry
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        panel = app.query_one(DetailPanel)
        panel.show_node(("system", [0]))
        await pilot.pause()
        text = str(panel.content)
        assert "nothing on file" in text
        assert "@click=app.fetch_intel(" in text

        sid = lookup_system("J105443").system_id
        # An old kill: details still shown, plus the quiet verdict.
        app.session.zkill_stats[sid] = SystemIntel(
            stats=None,
            last_kill=LastKill(
                time=utcnow() - timedelta(days=3),
                ship_name="Heron", attackers=2, isk=5_000_000.0,
            ),
        )
        panel.show_node(("system", [0]))
        text = str(panel.content)
        assert "LAST KILL: 3d ago — Heron" in text
        assert "QUIET" in text

        # No kill on record at all.
        app.session.zkill_stats[sid] = SystemIntel(stats=None, last_kill=None)
        panel.show_node(("system", [0]))
        text = str(panel.content)
        assert "LAST KILL: none on record" in text and "QUIET" in text


@pytest.mark.asyncio
async def test_dossier_auto_intel(tmp_path, monkeypatch):
    """Opening a dossier dispatches the killboard inquiry itself — once."""
    from vagari.enrichers import zkill

    calls = []

    async def fake_fetch(system_id):
        calls.append(system_id)
        return zkill.SystemIntel(
            stats=zkill.SystemKillStats(42, 9_000_000_000.0, 3, 2),
            last_kill=None,
        )

    monkeypatch.setattr(zkill, "fetch_system_intel", fake_fetch)
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        app.recon_enabled = True  # flipped late so startup stays offline
        panel = app.query_one(DetailPanel)
        panel.show_node(("system", [0]))
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        text = str(panel.content)
        assert "42" in text and "9.0B" in text and "ships" in text
        panel.show_node(("system", [0]))
        await pilot.pause()
        assert len(calls) == 1  # answered: no second inquiry


@pytest.mark.asyncio
async def test_dossier_opens_on_you(tmp_path):
    """The instrument opens with ◉ YOU's dossier on display, not a blank
    form — enrichment must have somewhere visible to land."""
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(DetailPanel)
        assert panel._showing == ("system", [0])
        assert "J105443" in str(panel.content)


@pytest.mark.asyncio
async def test_wormhole_sig_shows_far_side_killboard(tmp_path):
    """Intel belongs on this side of the hole: the sig dossier carries the
    destination's killboard section, before anyone splashes anything."""
    app = make_app(tmp_path)  # recon off: states render, no network
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        app.session.execute("qlm J154535")
        app.refresh_all()
        panel = app.query_one(DetailPanel)
        panel.show_node(("sig", [0], "QLM"))
        await pilot.pause()
        text = str(panel.content)
        assert "leads to" in text and "J154535" in text
        assert "WHAT AWAITS" in text  # far-side intel section present
        # Far side unnamed → still says something, asks nothing.
        app.session.file_k162()
        app.session.follow("?")
        panel.show_node(("sig", [0], "QLM"))
        assert "WHAT AWAITS" in str(panel.content)


@pytest.mark.asyncio
async def test_tick_relabels_in_place(tmp_path):
    """The minute tick advances ages without tearing the tree down —
    same nodes, fresh labels, no flicker-inducing clear()."""
    from datetime import timedelta

    from vagari.model.chain import utcnow

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        app.session.execute("qlm J154535")
        app.refresh_all()
        await pilot.pause()
        tree = app.query_one(ChainTree)
        assert tree.move_to_data(("sig", [0], "FIY"))
        node_before = tree.cursor_node
        spans_before = list(node_before.label.spans)

        for sig in app.session.chain.root.sigs:
            sig.last_seen = utcnow() - timedelta(hours=72)  # past STALE_HOURS
        app._tick()
        await pilot.pause()

        # Same node object — labels updated in place, no clear()/re-add.
        assert tree.cursor_node is node_before
        # Staleness is a color: the freshness dot's span changed style.
        assert list(node_before.label.spans) != spans_before


@pytest.mark.asyncio
async def test_arrival_choice_in_dossier(tmp_path):
    """An ambiguous arrival puts the passage choice in ◉ YOU's dossier as
    click targets; picking one files the system through that hole."""
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.session.ingest("XPA-001\tCosmic Signature\tWormhole\t\t40.0%\t1 AU")
        app.session.ingest("UNB-001\tCosmic Signature\tWormhole\t\t40.0%\t1 AU")
        msg = app.session.follow("J154535")
        assert "which passage" in msg
        app.refresh_all()
        await pilot.pause()
        panel = app.query_one(DetailPanel)
        panel.show_node(("system", [0]))
        text = str(panel.content)
        assert "ARRIVAL UNFILED: J154535" in text
        assert "run_cmd('k162 XPA')" in text and "run_cmd('k162 UNB')" in text
        assert "run_cmd('k162!')" in text

        app.action_run_cmd("k162 XPA")
        await pilot.pause()
        assert app.session.pending_arrival is None
        conn = app.session.chain.root.find_connection("XPA")
        assert conn is not None and conn.child.name == "J154535"
        assert "ARRIVAL UNFILED" not in str(panel.content)
