"""Follow-me: session location logic + the chatlog tailer."""

import asyncio
from pathlib import Path

import pytest

from vagari.followme.logtail import (
    LocalEvent,
    parse_listener,
    parse_system_change,
    tail_local_files,
)
from vagari.model.chain import Signature, SigGroup
from vagari.model.store import Store
from vagari.session import Session

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


def test_arrival_resolves_single_unknown_hole(tmp_path):
    """Field-reported: jumping through a typed hole whose far side is '?'
    must name that far side, not spawn a duplicate sibling placeholder."""
    sess = Session.open(Store(base_dir=tmp_path / "state"))
    sess.chain.root.name = "J103529"
    sess.ingest("HUV-843\tCosmic Signature\tWormhole\tUnstable Wormhole\t100.0%\t1 AU")
    sess.execute("huv U210")            # opens HUV → "?" (books lowsec)
    msg = sess.follow("J141150")        # the actual arrival
    assert "Assumed you took HUV" in msg
    assert "J141150" in msg
    assert "verify the type" in msg     # U210 books L; J141150 is C1
    assert sess.pending_arrival is None
    assert sess.chain.location == ["HUV"]
    child = sess.chain.root.find_connection("HUV").child
    assert child.name == "J141150"
    assert child.jclass == "C1"         # renamed AND re-enriched
    assert len(sess.chain.root.connections) == 1  # no duplicate sibling


def test_rekey_merges_duplicate_sibling(tmp_path):
    """Cleanup for chains already bearing the duplicate: `zaa = huv` folds
    the placeholder branch into the opened hole with the '?' far side."""
    sess = Session.open(Store(base_dir=tmp_path / "state"))
    sess.chain.root.name = "J103529"
    sess.ingest("HUV-843\tCosmic Signature\tWormhole\tUnstable Wormhole\t100.0%\t1 AU")
    sess.execute("huv U210")            # HUV → "?"
    sess.pending_arrival = ("J141150", [])
    sess.file_k162()                    # the old bug: ZAA → J141150 sibling
    sess.chain.current().sigs.append(Signature(sig_id="INA-123"))
    assert len(sess.chain.root.connections) == 2

    msg = sess.execute("zaa = huv")     # standing inside via ZAA
    assert "merged into HUV" in msg and "J141150" in msg
    root = sess.chain.root
    assert len(root.connections) == 1
    conn = root.find_connection("HUV")
    assert conn.child.name == "J141150"
    assert conn.child.find_sig("INA") is not None   # subtree survives
    assert conn.wh_type == "U210"                   # typed side wins
    assert root.find_sig("ZAA") is None
    assert sess.chain.location == ["HUV"]           # path follows the merge
    assert sess.chain.current().name == "J141150"


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
    # EVE writes a BOM at the start of every message line.
    assert parse_system_change("﻿" + line) == "Jita"
    assert parse_system_change("[ 2026.08.06 12:00:00 ] Some Pilot > o7") is None
    assert parse_system_change("garbage") is None


def header(listener: str) -> list[str]:
    return [
        "﻿",
        "  ---------------------------------------",
        "  Channel ID:      local",
        "  Channel Name:    Local",
        f"  Listener:        {listener}",
        "  Session started: 2026.08.06 12:00:00",
        "  ---------------------------------------",
    ]


def sysline(name: str, ts: str = "2026.08.06 12:00:00") -> str:
    return f"﻿[ {ts} ] EVE System > Channel changed to Local : {name}"


def chatline(pilot: str, text: str) -> str:
    return f"﻿[ 2026.08.06 12:30:00 ] {pilot} > {text}"


def write_log(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-16-le")


def test_parse_listener():
    assert parse_listener("\n".join(header("Cormorant Fell"))) == "Cormorant Fell"
    assert parse_listener("no header here") is None


@pytest.mark.asyncio
async def test_multibox_tailing(tmp_path):
    """Two live clients: events carry the right pilot; spam in one file does
    not disturb the other; replay yields one initial event per pilot."""
    hunter = tmp_path / "Local_20260806_100000_111.txt"
    trader = tmp_path / "Local_20260806_100001_222.txt"
    write_log(hunter, header("Hunter") + [sysline("J105443")])
    write_log(trader, header("Trader") + [sysline("Jita")])

    events: list[LocalEvent] = []

    async def on_event(e: LocalEvent) -> None:
        events.append(e)

    task = asyncio.create_task(tail_local_files(tmp_path, on_event, poll_interval=0.02))
    try:
        await asyncio.sleep(0.1)
        assert {(e.pilot, e.system, e.initial) for e in events} == {
            ("Hunter", "J105443", True),
            ("Trader", "Jita", True),
        }

        # Trade-hub spam bumps the trader file: no system events at all.
        with open(trader, "a", encoding="utf-16-le") as f:
            f.write(chatline("Spammer", "HyperNet offer: Golem") + "\n")
        await asyncio.sleep(0.1)
        assert len(events) == 2

        # The hunter jumps: a live event tagged with the right pilot.
        with open(hunter, "a", encoding="utf-16-le") as f:
            f.write(sysline("J154535") + "\n")
        await asyncio.sleep(0.1)
        assert events[-1] == LocalEvent("Hunter", "J154535", False)
    finally:
        task.cancel()
        await task


@pytest.mark.asyncio
async def test_tail_picks_up_new_session_file(tmp_path):
    events: list[LocalEvent] = []

    async def on_event(e: LocalEvent) -> None:
        events.append(e)

    task = asyncio.create_task(tail_local_files(tmp_path, on_event, poll_interval=0.02))
    try:
        await asyncio.sleep(0.05)
        assert events == []
        late = tmp_path / "Local_20260806_110000_333.txt"
        write_log(late, header("Latecomer") + [sysline("Amarr")])
        await asyncio.sleep(0.1)
        assert events == [LocalEvent("Latecomer", "Amarr", True)]
    finally:
        task.cancel()
        await task


# -- multibox follow policy ---------------------------------------------------

def test_follow_event_locks_on_first_live_jump(session):
    # Initial positions never move the marker without a lock.
    assert session.follow_event("Trader", "Jita", initial=True) is None
    assert session.chain.location == []

    # First live jump takes the lock.
    msg = session.follow_event("Hunter", "J154535", initial=False)
    assert "FOLLOWING Hunter" in msg
    assert session.pilot_lock == "Hunter"
    assert session.chain.location == ["QLM"]

    # Other pilots' jumps are ignored once locked.
    assert session.follow_event("Trader", "Perimeter", initial=False) is None
    assert session.chain.location == ["QLM"]


def test_pilot_command_reports_and_switches(session):
    session.follow_event("Trader", "Jita", initial=True)
    session.follow_event("Hunter", "J154535", initial=False)

    report = session.pilot_command(None)
    assert "Hunter" in report and "Trader" in report and "Following: Hunter" in report

    msg = session.pilot_command("trader")  # case-insensitive
    assert "FOLLOWING Trader" in msg
    assert session.pilot_lock == "Trader"

    assert "first pilot to jump" in session.pilot_command("off")
    assert session.pilot_lock is None


def test_pilot_lock_applies_initial_position(session):
    session.pilot_lock = "Hunter"
    msg = session.follow_event("Hunter", "J154535", initial=True)
    assert msg is not None
    assert session.chain.location == ["QLM"]


def test_pilot_lock_survives_restart(tmp_path):
    store = Store(base_dir=tmp_path / "state")
    sess = Session.open(store)
    sess.chain.root.name = "J105443"
    sess.follow_event("Hunter", "Jita", initial=False)  # auto-lock persists
    assert sess.pilot_lock == "Hunter"

    # A fresh session (restart) loads the lock, so initial replay syncs.
    again = Session.open(Store(base_dir=tmp_path / "state"))
    assert again.pilot_lock == "Hunter"

    again.pilot_command("off")
    third = Session.open(Store(base_dir=tmp_path / "state"))
    assert third.pilot_lock is None


def test_unmapped_arrival_is_sticky_in_header(tmp_path):
    # UI-level: the pending arrival badge lives in the header, not just the
    # transient status line that auto-recon overwrites.
    import asyncio

    from textual.widgets import Static

    from vagari.main import MapperApp

    async def run() -> str:
        sess = Session.open(Store(base_dir=tmp_path / "state"))
        sess.chain.root.name = "J103529"
        app = MapperApp(session=sess, recon=False, follow=False)
        async with app.run_test() as pilot:
            sess.follow_event("Cormorant Fell", "Vard", initial=False)
            app.refresh_all()
            await pilot.pause()
            return str(app.query_one("#header-status", Static).content)

    header = asyncio.run(run())
    assert "UNMAPPED: Vard" in header and "press k" in header


def test_cold_start_shows_not_following_hint(tmp_path):
    import asyncio

    from textual.widgets import Static

    from vagari.main import MapperApp

    async def run() -> str:
        sess = Session.open(Store(base_dir=tmp_path / "state"))
        app = MapperApp(session=sess, recon=False, follow=False)
        async with app.run_test() as pilot:
            app._follow_active = True  # as if the tailer started, no lock yet
            app.refresh_all()
            await pilot.pause()
            return str(app.query_one("#header-status", Static).content)

    header = asyncio.run(run())
    assert "NOT FOLLOWING" in header and "pilot" in header
