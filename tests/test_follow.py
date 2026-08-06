"""Follow-me: session location logic + the chatlog tailer."""

import asyncio
from pathlib import Path

import pytest

from tuimapper.followme.logtail import (
    latest_local_log,
    parse_system_change,
    tail_system_changes,
)
from tuimapper.model.chain import SigGroup
from tuimapper.model.store import Store
from tuimapper.session import Session

FIXTURES = Path(__file__).parent / "fixtures"


# -- session.follow ----------------------------------------------------------

@pytest.fixture
def session(tmp_path):
    sess = Session.open(Store(base_dir=tmp_path / "state"))
    sess.chain.root.name = "J105443"
    sess.ingest((FIXTURES / "paste_mixed.txt").read_text())
    sess.execute("qlm J154535")
    return sess


def test_follow_noop_when_already_there(session):
    assert session.follow("J105443") is None


def test_follow_into_child(session):
    msg = session.follow("J154535")
    assert "Followed you through QLM" in msg
    assert session.chain.location == ["QLM"]


def test_follow_back_to_parent(session):
    session.follow("J154535")
    msg = session.follow("J105443")
    assert "back up" in msg
    assert session.chain.location == []


def test_follow_finds_system_elsewhere_in_chain(session):
    session.execute("nav qlm")
    session.ingest((FIXTURES / "paste_second.txt").read_text())
    session.execute("asd J164417")
    session.execute("top")
    # Pilot appears two jumps deep while the marker sits at the root.
    msg = session.follow("J164417")
    assert "elsewhere in the chain" in msg
    assert session.chain.location == ["QLM", "ASD"]


def test_follow_unmapped_offers_k162(session):
    msg = session.follow("J100744")
    assert "UNMAPPED" in msg and "k162" in msg.lower()
    assert session.pending_arrival == ("J100744", [])
    assert session.chain.location == []  # marker does not move on speculation


def test_file_k162_creates_placeholder(session):
    session.follow("J100744")
    msg = session.file_k162()
    assert "ZAA" in msg
    origin = session.chain.root
    sig = origin.find_sig("ZAA")
    assert sig.group is SigGroup.WORMHOLE
    assert sig.label == "K162 (unscanned)"
    conn = origin.find_connection("ZAA")
    assert conn.wh_type == "K162"
    assert conn.child.name == "J100744"
    assert conn.child.jclass == "C1"  # enriched from catalog
    assert conn.child.effect == "Cataclysmic Variable"
    assert session.chain.location == ["ZAA"]
    assert session.pending_arrival is None


def test_file_k162_without_pending(session):
    assert "at peace" in session.file_k162()


def test_fresh_chain_root_named_by_first_arrival(tmp_path):
    sess = Session.open(Store(base_dir=tmp_path / "s2"))
    msg = sess.follow("J154535")
    assert "on record as J154535" in msg
    assert sess.chain.root.name == "J154535"
    assert sess.chain.root.jclass == "C1"
    assert sess.chain.root.effect == "Black Hole"


def test_here_command(session):
    session.execute("nav qlm")
    msg = session.execute("here J100744")
    assert "on record as J100744" in msg
    assert session.chain.current().name == "J100744"
    assert session.chain.current().jclass == "C1"


# -- chatlog parsing / tailing ----------------------------------------------

def test_parse_system_change():
    line = "[ 2026.08.06 12:00:00 ] EVE System > Channel changed to Local : Jita"
    assert parse_system_change(line) == "Jita"
    assert parse_system_change("[ 2026.08.06 12:00:00 ] Some Pilot > o7") is None
    assert parse_system_change("garbage") is None


def write_log(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-16-le")


def sysline(name: str, ts: str = "2026.08.06 12:00:00") -> str:
    return f"[ {ts} ] EVE System > Channel changed to Local : {name}"


def test_latest_local_log(tmp_path):
    assert latest_local_log(tmp_path) is None
    a = tmp_path / "Local_20260806_100000.txt"
    write_log(a, [sysline("Jita")])
    assert latest_local_log(tmp_path) == a


@pytest.mark.asyncio
async def test_tail_replays_only_last_then_streams(tmp_path):
    log = tmp_path / "Local_20260806_100000.txt"
    write_log(log, [sysline("Jita"), sysline("Perimeter")])

    seen: list[str] = []

    async def on_system(name: str) -> None:
        seen.append(name)

    task = asyncio.create_task(
        tail_system_changes(tmp_path, on_system, poll_interval=0.02)
    )
    try:
        await asyncio.sleep(0.1)
        assert seen == ["Perimeter"]  # history replay yields only the last

        with open(log, "a", encoding="utf-16-le") as f:
            f.write(sysline("J105443") + "\n")
        await asyncio.sleep(0.1)
        assert seen == ["Perimeter", "J105443"]
    finally:
        task.cancel()
        await task


@pytest.mark.asyncio
async def test_tail_switches_to_newer_log(tmp_path):
    old = tmp_path / "Local_20260806_100000.txt"
    write_log(old, [sysline("Jita")])

    seen: list[str] = []

    async def on_system(name: str) -> None:
        seen.append(name)

    task = asyncio.create_task(
        tail_system_changes(tmp_path, on_system, poll_interval=0.02)
    )
    try:
        await asyncio.sleep(0.1)
        assert seen == ["Jita"]

        new = tmp_path / "Local_20260806_110000.txt"
        write_log(new, [sysline("Amarr")])
        import os
        os.utime(new, None)
        await asyncio.sleep(0.15)
        assert seen == ["Jita", "Amarr"]
    finally:
        task.cancel()
        await task
