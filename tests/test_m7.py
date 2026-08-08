"""M7: export, rekey, cull, amend-commits, graphs, sampling, staleness."""

from datetime import timedelta
from pathlib import Path

import pytest

from vagari.export import export_text
from vagari.model.chain import ChainError, utcnow
from vagari.model.store import Store
from vagari.session import Session
from vagari.ui.chain_tree import sig_label
from vagari.ui.graphs import gauge, spark

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def session(tmp_path):
    sess = Session.open(Store(base_dir=tmp_path / "state"))
    sess.chain.root.name = "J105443"
    sess.ingest((FIXTURES / "paste_mixed.txt").read_text())
    sess.execute("qlm J154535")
    return sess


# -- export ------------------------------------------------------------------

def test_export_text_structure(session):
    session.execute("nav qlm")
    text = export_text(session.chain)
    assert text.splitlines()[0].startswith("J105443")
    assert "└→ J154535 [C1+N · Black Hole] ◉ YOU" in text
    assert "○ WORMHOLE QLM" in text and "◈ RELIC" in text
    assert "VAGARI · chain home" in text
    assert "[" not in text.splitlines()[1][:2]  # no markup leaked


def test_export_paths_view_filters(session):
    text = export_text(session.chain, view="paths")
    assert "QLM" in text and "FIY" not in text


# -- rekey -------------------------------------------------------------------

def test_rekey_placeholder_preserves_subtree(session):
    session.follow("J100744")
    session.file_k162()          # creates ZAA → J100744, moves into it
    session.execute("up")
    msg = session.execute("zaa = htx")
    assert "ZAA refiled as HTX" in msg
    conn = session.chain.current().find_connection("HTX")
    assert conn is not None and conn.child.name == "J100744"
    sig = session.chain.current().find_sig("HTX")
    assert sig.label == ""       # placeholder label cleared
    assert session.chain.current().find_sig("ZAA") is None
    # The real paste now merges into the refiled sig.
    session.ingest("HTX-123\tCosmic Signature\tWormhole\tUnstable Wormhole\t100.0%\t1 AU")
    assert session.chain.current().find_sig("HTX").signal == 100.0


def test_rekey_rejects_collisions(session):
    assert "REFUSED" in session.execute("rekey qlm fiy")  # FIY is a relic
    assert "REFUSED" in session.execute("rekey zzz abc")


def test_rekey_from_inside_the_hole(session):
    """Field-reported: after filing a K162 you are standing INSIDE it —
    the placeholder lives one hole up, and the location path must follow
    the rename."""
    session.follow("J100744")
    session.file_k162()                      # ZAA → J100744, we are inside
    assert session.chain.location == [0, "ZAA"]
    msg = session.execute("zaa = kdx")       # no `up` required
    assert "refiled as KDX" in msg
    assert session.chain.location == [0, "KDX"]
    assert session.chain.current().name == "J100744"  # path still resolves
    parent = session.chain.root
    assert parent.find_connection("KDX").child.name == "J100744"
    assert parent.find_sig("ZAA") is None


def test_rekey_absorbs_scanned_real_sig(session):
    """The common flow: file a K162, then paste — the real sig appears as its
    own row; rekey absorbs the placeholder into the scanned record."""
    session.follow("J100744")
    session.file_k162()          # ZAA → J100744
    session.execute("up")
    session.ingest(
        "KDX-427\tCosmic Signature\tWormhole\tUnstable Wormhole\t100.0%\t2 AU"
    )
    msg = session.execute("zaa = kdx")
    assert "absorbed into KDX" in msg
    here = session.chain.current()
    assert here.find_sig("ZAA") is None
    kdx = here.find_sig("KDX")
    assert kdx.sig_id == "KDX-427"      # the real scanned id survives
    assert kdx.signal == 100.0
    conn = here.find_connection("KDX")
    assert conn is not None and conn.child.name == "J100744"
    assert conn.wh_type is None  # placeholder holes carry no type


# -- cull --------------------------------------------------------------------

def test_cull_strikes_expired(session):
    session.execute("qlm N110")  # sets type; wait — QLM already opened
    conn = session.chain.current().find_connection("QLM")
    conn.wh_type = "N110"
    conn.opened_at = utcnow() - timedelta(hours=30)  # past 24h book life
    msg = session.execute("cull")
    assert "Culled: QLM" in msg
    assert session.chain.current().find_sig("QLM") is None


def test_cull_severs_children_into_fragment(session):
    conn = session.chain.current().find_connection("QLM")
    conn.wh_type = "N110"
    conn.opened_at = utcnow() - timedelta(hours=30)
    session.execute("nav qlm")
    session.ingest((FIXTURES / "paste_second.txt").read_text())
    session.execute("top")
    msg = session.execute("cull")
    # An expired hole with mapped children is not destroyed and not
    # retained — its far side becomes a free-floating fragment.
    assert "severed" in msg and "fragment #2" in msg
    assert session.chain.current().find_sig("QLM") is None
    assert len(session.chain.roots) == 2
    assert session.chain.roots[1].name == "J154535"
    assert session.chain.roots[1].find_sig("ZZT") is not None  # subtree intact


def test_cull_nothing(session):
    assert "Nothing past" in session.execute("cull")


# -- location commits amend, mapping commits append --------------------------

def test_nav_does_not_burn_undo(session, tmp_path):
    snaps_dir = tmp_path / "state" / "home"
    before = len(list(snaps_dir.glob("snap-*.json")))
    session.execute("nav qlm")
    session.execute("up")
    session.execute("nav qlm")
    session.execute("top")
    after = len(list(snaps_dir.glob("snap-*.json")))
    assert after == before  # roaming amends; it does not append

    session.execute("flag fiy")  # a mapping change appends
    assert len(list(snaps_dir.glob("snap-*.json"))) == before + 1


def test_follow_roam_preserves_undo_of_mapping(session):
    session.execute("flag fiy")
    session.follow("J154535")
    session.follow("J105443")
    assert "Reverted" in session.undo()
    assert not session.chain.current().find_sig("FIY").flagged


# -- graphs ------------------------------------------------------------------

def test_gauge():
    assert gauge(1.0) == "▰▰▰▰▰▰"
    assert gauge(0.0) == "▱▱▱▱▱▱"
    assert gauge(0.5) == "▰▰▰▱▱▱"
    assert gauge(2.0) == "▰▰▰▰▰▰"
    assert gauge(1.0, cells=3) == "▰▰▰"


def test_spark():
    assert spark([]) == ""
    assert spark([0, 0]) == "▁▁"
    s = spark([0, 4, 8])
    assert len(s) == 3 and s[0] == "▁" and s[-1] == "█"


# -- activity sampling -------------------------------------------------------

def test_sample_activity_tracks_chain_systems(session):
    from vagari.enrichers.activity import SystemActivity
    from vagari.parsers.catalog import lookup_system

    sid = lookup_system("J105443").system_id
    session.activity = {sid: SystemActivity(2, 1, 0)}
    session.sample_activity()
    session.activity = {}
    session.sample_activity()
    assert session.activity_history[sid] == [3, 0]


# -- staleness rendering -----------------------------------------------------

def test_kind_column_words():
    from vagari.glyphs import kind_word
    from vagari.model.chain import SigGroup

    assert kind_word(SigGroup.WORMHOLE) == "WORMHOLE"
    assert kind_word(SigGroup.RELIC, "Ruined Guristas Crystal Quarry") == "RELIC"
    assert kind_word(SigGroup.DATA, "Guristas Covert Research Facility") == "GHOST"
    assert kind_word(SigGroup.UNKNOWN) == "UNFILED"


def test_sig_label_new_and_stale(session):
    now = utcnow()
    sig = session.chain.current().find_sig("FIY")
    assert "●" in sig_label(sig, None, now=now)  # freshly filed

    sig.first_seen = now - timedelta(hours=12)
    sig.last_seen = now - timedelta(hours=12)
    label = sig_label(sig, None, now=now)
    assert "●" not in label
    assert "unconfirmed" in label
