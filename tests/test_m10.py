"""M10: EOL countdown, fleet markers, chain persistence, global cull,
copy route, system staleness, watchtower, fragment hygiene."""

from datetime import timedelta
from pathlib import Path

import pytest

from vagari.model.chain import Chain, Connection, System, utcnow
from vagari.model.lifetime import LifeStatus, assess
from vagari.model.store import Store
from vagari.session import Session

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def session(tmp_path):
    sess = Session.open(Store(base_dir=tmp_path / "state"))
    sess.chain.root.name = "J105443"
    sess.ingest((FIXTURES / "paste_mixed.txt").read_text())
    sess.execute("qlm J154535")
    return sess


# 1 — EOL counts down from the marking
def test_eol_counts_down_from_marking(session):
    session.execute("qlm N110" if False else "eol qlm")
    conn = session.chain.root.find_connection("QLM")
    conn.wh_type = "N110"
    assert conn.eol_marked_at is not None
    two_h = conn.eol_marked_at + timedelta(hours=2)
    life = assess(conn, now=two_h)
    assert life.status is LifeStatus.EOL
    assert abs(life.remaining_hours - 2.0) < 0.01  # 4h clock, 2h elapsed

    session.execute("eol qlm")  # un-mark clears the clock
    assert conn.eol_marked_at is None


# 2 — fleet markers
@pytest.mark.asyncio
async def test_fleet_markers_render(tmp_path):
    from tests.test_app import make_app, paste, tree_text
    from vagari.ui.chain_tree import ChainTree

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        app.session.pilot_lock = "Hunter"
        app.session.known_pilots = {
            "Hunter": "J105443", "Trader": "J105443", "Scout": "Jita",
        }
        app.refresh_all()
        await pilot.pause()
        text = tree_text(app.query_one(ChainTree))
        assert "◎ Trader" in text          # fleetmate here
        assert "◎ Hunter" not in text      # the followed pilot is ◉ YOU
        assert "◎ Scout" not in text       # not in any mapped system


# 3 — active chain persists
def test_active_chain_persists(tmp_path):
    store = Store(base_dir=tmp_path / "state")
    sess = Session.open(store)
    sess.execute("chain staging")
    again = Session.open(Store(base_dir=tmp_path / "state"))
    assert again.chain.name == "staging"


# 4 — chain-wide cull
def test_cull_reaches_the_whole_forest(session):
    session.execute("nav qlm")
    session.ingest((FIXTURES / "paste_second.txt").read_text())
    session.execute("zzt J100744")
    deep = session.chain.current().find_connection("ZZT")
    deep.wh_type = "N110"
    deep.opened_at = utcnow() - timedelta(hours=30)
    session.execute("top")
    session.execute("fragment J164417")   # stand in a different fragment
    msg = session.execute("cull")
    assert "ZZT" in msg and "J154535" in msg  # culled two hops away


# 6 — system staleness badge
def test_system_staleness_badge(session):
    from vagari.ui.chain_tree import system_label

    root = session.chain.root
    now = utcnow()
    for sig in root.sigs:
        sig.last_seen = now - timedelta(hours=9)
    label = system_label(root, here=False, now=now)
    assert "(scanned 9h00m ago)" in label
    fresh = system_label(root, here=False, now=now - timedelta(hours=9))
    assert "scanned" not in fresh


# 7 — watchtower alerts
def test_watchtower_alerts_on_new_hostility(session):
    from vagari.enrichers.activity import SystemActivity
    from vagari.parsers.catalog import lookup_system

    sid = lookup_system("J105443").system_id
    session.activity = {}
    assert session.sample_activity() == []          # quiet baseline
    session.activity = {sid: SystemActivity(3, 1, 0)}
    alerts = session.sample_activity()
    assert alerts and "J105443" in alerts[0] and "4 PvP kills" in alerts[0]
    # Staying hostile does not re-alert.
    assert session.sample_activity() == []


# 8 — fragment hygiene
def test_discard_fragment(session):
    session.execute("fragment J100744")
    session.execute("chain" if False else "top")
    assert len(session.chain.roots) == 2
    # Striking the fragment you occupy relocates ◉ YOU out of it first.
    msg = session.execute("discard 2")
    assert "struck" in msg and "relocated" in msg
    assert session.chain.location == [0]
    assert len(session.chain.roots) == 1
    assert "only fragment" in session.execute("discard 1")


def test_discard_guards_content(session):
    session.execute("sever qlm")   # fragment 2 has mapped content? (empty child)
    session.chain.roots[1].sigs.append(
        __import__("vagari.model.chain", fromlist=["Signature"]).Signature(
            sig_id="AAA-111"
        )
    )
    session.chain.location = [0]
    q = session.execute("discard 2")
    assert "CONFIRM" in q and "y/n" in q
    assert len(session.chain.roots) == 2         # a question mutates nothing
    assert "stands" in session.execute("n")      # declined
    assert len(session.chain.roots) == 2
    session.execute("discard 2")
    assert "struck" in session.execute("y")      # confirmed
    assert len(session.chain.roots) == 1


def test_adrift_age_stamped(session):
    session.execute("sever qlm")
    assert session.chain.roots[1].adrift_since is not None
    session.ingest("NEW-001\tCosmic Signature\tWormhole\t\t60.0%\t1 AU")
    session.execute("new J154535")   # adoption clears the stamp
    conn = session.chain.root.find_connection("NEW")
    assert conn.child.adrift_since is None


def test_discard_by_name(session):
    session.execute("fragment Knophtikoo")
    session.chain.location = [0]
    assert "struck" in session.execute("discard knop")
    session.execute("fragment J100744")
    session.execute("fragment J164417")
    session.chain.location = [0]
    # Ambiguous prefixes refuse with candidates; exact numbers still work.
    assert "no fragment" in session.execute("discard nope")
    assert "struck" in session.execute("discard j100744")


@pytest.mark.asyncio
async def test_d_key_discards_selected_fragment(tmp_path):
    from tests.test_app import make_app, paste
    from vagari.ui.chain_tree import ChainTree

    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await paste(app, pilot, "paste_mixed.txt")
        app.session.execute("fragment J100744")
        app.session.chain.location = [0]
        app.refresh_all()
        await pilot.pause()
        tree = app.query_one(ChainTree)
        assert tree.move_to_data(("system", [1]))
        await pilot.press("d")
        await pilot.pause()
        assert len(app.session.chain.roots) == 1


def test_striking_only_fragment_resets_map(session):
    """The map must map something — so striking the last fragment begins
    a fresh one instead of refusing, leaving no bogus root to be stuck in."""
    q = session.execute("strike J105443")
    assert "CONFIRM" in q and "resets the map" in q
    assert session.chain.root.name == "J105443"    # question mutates nothing
    session.execute("y")
    assert session.chain.root.name == "HOME"
    assert session.chain.root.sigs == []
    assert session.chain.location == [0]
    # Fresh-chain naming re-arms: the next observed system names the root.
    session.follow("J103529")
    assert session.chain.root.name == "J103529"
