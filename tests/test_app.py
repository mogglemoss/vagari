"""Headless UI smoke tests via Textual's pilot."""

from pathlib import Path

import pytest
from textual import events
from textual.widgets import Static

from tuimapper.main import MapperApp
from tuimapper.model.store import Store
from tuimapper.session import Session
from tuimapper.ui.chain_tree import ChainTree
from tuimapper.ui.help_screen import HelpScreen

FIXTURES = Path(__file__).parent / "fixtures"


def make_app(tmp_path) -> MapperApp:
    session = Session.open(Store(base_dir=tmp_path / "state"))
    session.chain.root.name = "J105443"
    return MapperApp(session=session)


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
async def test_view_filter(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        await pilot.press("2")  # paths: wormholes only
        await pilot.pause()
        text = tree_text(app.query_one(ChainTree))
        assert "QLM" in text and "FIY" not in text
