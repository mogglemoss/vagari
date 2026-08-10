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
        assert "CANDIDATE TYPES" in text
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

        table.move_cursor(row=2)  # FIY
        table.action_select_cursor()
        await pilot.pause()
        assert app.query_one(ChainTree).cursor_node.data == ("sig", [0], "FIY")


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
