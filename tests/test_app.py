"""Headless UI smoke tests via Textual's pilot."""

from pathlib import Path

import pytest
from textual import events
from textual.widgets import Static

from vagari.main import MapperApp
from vagari.model.store import Store
from vagari.session import Session
from vagari.ui.chain_tree import ChainTree
from vagari.ui.help_screen import HelpScreen

FIXTURES = Path(__file__).parent / "fixtures"


def make_app(tmp_path, **kwargs) -> MapperApp:
    session = Session.open(Store(base_dir=tmp_path / "state"))
    session.chain.root.name = "J105443"
    kwargs.setdefault("recon", False)
    kwargs.setdefault("follow", False)
    return MapperApp(session=session, **kwargs)


def tree_text(tree: ChainTree) -> str:
    """All node labels, flattened to plain text."""
    parts = []

    def walk(node):
        parts.append(str(node.label))
        for child in node.children:
            walk(child)

    walk(tree.root)
    return "\n".join(parts)


async def paste(app, pilot, name: str) -> None:
    app.post_message(events.Paste((FIXTURES / name).read_text()))
    await pilot.pause()


@pytest.mark.asyncio
async def test_paste_populates_tree(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        text = tree_text(app.query_one(ChainTree))
        assert "QLM" in text and "FIY" in text
        assert "◉ YOU" in text
        status = str(app.query_one("#status-line", Static).content)
        assert "NEW" in status


@pytest.mark.asyncio
async def test_command_bar_open_and_nav(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        await pilot.press("colon")
        await pilot.press(*"qlm J154535")
        await pilot.press("enter")
        await pilot.pause()
        assert "J154535" in tree_text(app.query_one(ChainTree))

        await pilot.press("colon")
        await pilot.press(*"nav qlm")
        await pilot.press("enter")
        await pilot.pause()
        assert app.session.chain.current().name == "J154535"
        assert "J154535" in str(
            app.query_one("#header-breadcrumb", Static).content
        )


@pytest.mark.asyncio
async def test_undo_key(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        assert app.session.chain.current().sigs
        await pilot.press("z")
        await pilot.pause()
        assert app.session.chain.current().sigs == []


@pytest.mark.asyncio
async def test_help_screen(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_detail_panel_shows_activity(tmp_path):
    from vagari.enrichers.activity import SystemActivity
    from vagari.parsers.catalog import lookup_system
    from vagari.ui.detail_panel import DetailPanel

    app = make_app(tmp_path)
    sid = lookup_system("J105443").system_id
    app.session.activity = {sid: SystemActivity(ship_kills=3, pod_kills=1, npc_kills=5)}
    app.session.activity_fetched = True
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(DetailPanel)
        panel.show_node(("system", []))
        text = str(panel.content)
        assert "ACTIVITY" in text and "3 ship" in text


@pytest.mark.asyncio
async def test_follow_me_end_to_end(tmp_path, monkeypatch):
    """Real tailer + real app: a chatlog jump moves ◉ YOU and files a K162."""
    chatlogs = tmp_path / "Chatlogs"
    chatlogs.mkdir()
    monkeypatch.setenv("VAGARI_LOG_DIR", str(chatlogs))
    from vagari.followme.logtail import tail_local_files as real_tail

    monkeypatch.setattr(
        "vagari.main.tail_local_files",
        lambda d, cb: real_tail(d, cb, poll_interval=0.02),
    )

    log = chatlogs / "Local_20260806_100000_111.txt"
    log.write_text(
        "  Listener:        Hunter\n"
        "[ 2026.08.06 12:00:00 ] EVE System > Channel changed to Local : J105443\n",
        encoding="utf-16-le",
    )

    app = make_app(tmp_path, follow=True)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        await pilot.press("colon")
        await pilot.press(*"qlm J154535")
        await pilot.press("enter")
        await pilot.pause()

        # Jump through QLM in-game.
        with open(log, "a", encoding="utf-16-le") as f:
            f.write(
                "[ 2026.08.06 12:05:00 ] EVE System > Channel changed to Local : J154535\n"
            )
        for _ in range(20):
            await pilot.pause(0.05)
            if app.session.chain.location == ["QLM"]:
                break
        assert app.session.chain.location == ["QLM"]
        assert "◉ YOU" in tree_text(app.query_one(ChainTree))

        # Jump somewhere unmapped, then file it with `k`.
        with open(log, "a", encoding="utf-16-le") as f:
            f.write(
                "[ 2026.08.06 12:10:00 ] EVE System > Channel changed to Local : J100744\n"
            )
        for _ in range(20):
            await pilot.pause(0.05)
            if app.session.pending_arrival is not None:
                break
        assert app.session.pending_arrival == ("J100744", ["QLM"])

        await pilot.press("k")
        await pilot.pause()
        assert app.session.chain.location == ["QLM", "ZAA"]
        assert "J100744" in tree_text(app.query_one(ChainTree))


@pytest.mark.asyncio
async def test_about_screen_and_header(tmp_path):
    from vagari.ui.about_screen import AboutScreen
    from vagari.ui.widgets import VagariHeader

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        header = app.query_one(VagariHeader)
        breadcrumb = str(header.query_one("#header-breadcrumb", Static).content)
        assert "J105443" in breadcrumb

        await pilot.press("a")
        await pilot.pause()
        assert isinstance(app.screen, AboutScreen)
        text = str(app.screen.query_one("#about-box", Static).content)
        assert "bashmapper" in text and "anoik.is" in text
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, AboutScreen)


@pytest.mark.asyncio
async def test_detail_panel_site_intel(tmp_path):
    from vagari.ui.detail_panel import DetailPanel

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        panel = app.query_one(DetailPanel)
        panel.show_node(("sig", [], "FIY"))  # Ruined Guristas Crystal Quarry
        text = str(panel.content)
        assert "NO NPCS" in text and "best containers" in text


@pytest.mark.asyncio
async def test_command_palette_curated(tmp_path):
    app = make_app(tmp_path)
    commands = [c.title for c in app.get_system_commands(None)]
    assert "Recon: refresh activity" in commands
    assert "Arm lazy reconciliation" in commands
    assert not any("theme" in c.lower() for c in commands)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+p")
        await pilot.pause()
        from textual.command import CommandPalette

        assert any(isinstance(s, CommandPalette) for s in app.screen_stack)


@pytest.mark.asyncio
async def test_fzf_typing_starts_submission(tmp_path):
    from textual.widgets import Input

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        # 'n' is not an instant key: it should focus the bar seeded with 'n'.
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.focused, Input)
        await pilot.press(*"av qlm")
        # No connection yet, so nav refuses — but the submission executed.
        await pilot.press("enter")
        await pilot.pause()
        status = str(app.query_one("#status-line", Static).content)
        assert "REFUSED" in status
        assert not isinstance(app.focused, Input)  # focus returned to the map

        # Instant keys still act instantly: 'z' undoes, no submission starts.
        await pilot.press("z")
        await pilot.pause()
        assert not isinstance(app.focused, Input)

        # Escape withdraws a started submission; pasting afterwards ingests.
        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.focused, Input)
        await pilot.press("escape")
        await pilot.pause()
        await paste(app, pilot, "paste_mixed.txt")
        assert app.session.chain.current().sigs  # ingest reached the chain


@pytest.mark.asyncio
async def test_wormhole_type_mass_in_detail(tmp_path):
    from vagari.ui.detail_panel import DetailPanel, human_mass

    assert human_mass(3_000_000_000) == "3.0B kg"
    assert human_mass(5_000_000) == "5.0M kg"

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        await pilot.press("colon")
        await pilot.press(*"qlm N110")
        await pilot.press("enter")
        await pilot.pause()
        panel = app.query_one(DetailPanel)
        panel.show_node(("sig", [], "QLM"))
        text = str(panel.content)
        assert "N110" in text and "per jump ≤" in text and "total" in text


@pytest.mark.asyncio
async def test_search_moves_cursor_and_cycles(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        await pilot.press("colon")
        await pilot.press(*"qlm J154535")
        await pilot.press("enter")
        await pilot.pause()

        await pilot.press("slash")
        await pilot.press(*"J154535")
        await pilot.press("enter")
        await pilot.pause()
        tree = app.query_one(ChainTree)
        assert tree.cursor_node.data == ("system", ["QLM"])
        status = str(app.query_one("#status-line", Static).content)
        assert "Match 1/" in status

        # "j1" hits both systems; repeating the query cycles between them.
        await pilot.press("slash")
        await pilot.press(*"j1")
        await pilot.press("enter")
        await pilot.pause()
        first = app.query_one(ChainTree).cursor_node.data
        await pilot.press("slash")
        await pilot.press(*"j1")
        await pilot.press("enter")
        await pilot.pause()
        second = app.query_one(ChainTree).cursor_node.data
        assert first != second


@pytest.mark.asyncio
async def test_kspace_rendering(tmp_path):
    from vagari.enrichers.kspace import KSpaceInfo
    from vagari.ui.detail_panel import DetailPanel

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        app.session.follow("Jita")
        app.session.file_k162()
        app.session.kspace["Jita"] = KSpaceInfo(30000142, 0.9459, "The Forge")
        app.refresh_all()
        await pilot.pause()
        assert "0.9" in tree_text(app.query_one(ChainTree))

        from vagari.enrichers.zkill import SystemKillStats

        app.session.zkill_stats[30000142] = SystemKillStats(1_538_343, 795, 1354)
        panel = app.query_one(DetailPanel)
        panel.show_node(("system", ["ZAA"]))
        text = str(panel.content)
        assert "security 0.9" in text and "The Forge" in text
        assert "1,538,343 ships destroyed" in text


@pytest.mark.asyncio
async def test_view_filter(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        await pilot.press("2")  # paths: wormholes only
        await pilot.pause()
        text = tree_text(app.query_one(ChainTree))
        assert "QLM" in text and "FIY" not in text
