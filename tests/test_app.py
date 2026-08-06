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
        assert "J154535" in str(app.query_one("#app-header", Static).content)


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
    from vagari.followme.logtail import tail_system_changes as real_tail

    monkeypatch.setattr(
        "vagari.main.tail_system_changes",
        lambda d, cb: real_tail(d, cb, poll_interval=0.02),
    )

    log = chatlogs / "Local_20260806_100000.txt"
    log.write_text(
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
async def test_view_filter(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        await pilot.press("2")  # paths: wormholes only
        await pilot.pause()
        text = tree_text(app.query_one(ChainTree))
        assert "QLM" in text and "FIY" not in text
