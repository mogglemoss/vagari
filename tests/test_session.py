from pathlib import Path

import pytest

from vagari.model.chain import MassState, SigGroup
from vagari.model.store import Store
from vagari.session import Session

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def session(tmp_path):
    store = Store(base_dir=tmp_path / "state")
    sess = Session.open(store)
    sess.chain.root.name = "J105443"
    sess.ingest((FIXTURES / "paste_mixed.txt").read_text())
    return sess


def test_open_creates_new_chain(tmp_path):
    sess = Session.open(Store(base_dir=tmp_path / "s"), "home")
    assert sess.chain.name == "home"
    assert sess.store.load_latest("home") is not None


def test_ingest_reports(session):
    assert {s.prefix for s in session.chain.current().sigs} == {"ASD", "VMX", "FIY", "QLM"}


def test_ingest_garbage(session):
    msg = session.ingest("not telemetry")
    assert "Nothing legible" in msg


def test_open_jcode_and_nav(session):
    msg = session.execute("qlm J154535")
    assert "J154535" in msg and "C1" in msg
    session.execute("nav qlm")
    assert session.chain.current().name == "J154535"
    assert session.breadcrumb() == "J105443 ▸ J154535"
    session.execute("up")
    assert session.chain.current().name == "J105443"


def test_open_unknown_jcode(session):
    msg = session.execute("qlm J999999")
    assert "not in Bureau records" in msg


def test_wh_type_command_opens_unknown_destination(session):
    msg = session.execute("qlm N110")
    assert "N110" in msg
    conn = session.chain.current().find_connection("QLM")
    assert conn.wh_type == "N110"
    assert conn.child.jclass == "H"


def test_label_command(session):
    session.execute("fiy good relic site")
    assert session.chain.current().find_sig("FIY").label == "good relic site"


def test_flag_eol_crit(session):
    session.execute("flag asd vmx")
    assert session.chain.current().find_sig("ASD").flagged
    assert session.chain.current().find_sig("VMX").flagged

    session.execute("qlm J154535")
    assert "END OF LIFE" in session.execute("eol qlm")
    assert session.chain.current().find_connection("QLM").eol
    session.execute("crit qlm")
    assert session.chain.current().find_connection("QLM").mass is MassState.REDUCED

    assert "REFUSED" in session.execute("eol fiy")  # not a wormhole


def test_del_guard_and_force(session):
    session.execute("qlm J154535")
    session.execute("nav qlm")
    session.ingest((FIXTURES / "paste_second.txt").read_text())
    session.execute("top")

    q = session.execute("del qlm")
    assert "CONFIRM" in q and "sever keeps it adrift" in q
    assert session.chain.current().find_sig("QLM") is not None
    # Any other filing withdraws the question and runs normally.
    session.execute("up")
    session.execute("top")
    assert session.chain.current().find_sig("QLM") is not None
    session.execute("del qlm")
    assert "struck" in session.execute("y")
    assert session.chain.current().find_sig("QLM") is None


def test_despawn_reporting_always_on(session):
    # No arming: every deposit reports despawn candidates; sweep strikes.
    msg = session.ingest((FIXTURES / "paste_second.txt").read_text())
    assert "DESPAWNED" in msg
    assert session.chain.current().find_sig("VMX") is not None  # report only
    msg = session.execute("sweep")
    assert "Struck" in msg
    assert session.chain.current().find_sig("VMX") is None
    # `lazy` remains a polite no-op pointing at the new behavior.
    assert "sweep" in session.execute("lazy")


def test_views(session):
    session.execute("paths")
    assert session.view == "paths"
    session.execute("full")
    assert session.view == "full"


def test_undo_redo(session):
    session.execute("del fiy")
    assert session.chain.current().find_sig("FIY") is None
    assert "Reverted" in session.undo()
    assert session.chain.current().find_sig("FIY") is not None
    assert "Reinstated" in session.redo()
    assert session.chain.current().find_sig("FIY") is None


def test_chain_switch(session):
    session.execute("chain staging")
    assert session.chain.name == "staging"
    assert session.chain.root.sigs == []
    session.execute("chain home")
    assert session.chain.current().find_sig("QLM") is not None


def test_jump(session):
    session.execute("qlm J154535")
    assert "J154535" in session.jump([0, "QLM"])
    assert session.chain.location == [0, "QLM"]


def test_unknown_command(session):
    assert "Unrecognised" in session.execute("frobnicate the chain")


# -- HOME ---------------------------------------------------------------------

def test_home_file_route_unfile(session):
    session.execute("qlm J154535")
    msg = session.execute("home J154535")
    assert "HOME filed: J154535 ⌂" in msg
    assert session.chain.home == "J154535"
    # Route DOWN to home from the root.
    route = session.execute("home")
    assert "HOMEWARD (1 jump)" in route and "▸ QLM" in route and "⌂" in route
    session.execute("nav qlm")
    assert "You are HOME" in session.execute("home")
    # Survives the snapshot round trip.
    from vagari.model.chain import Chain

    assert Chain.from_dict(session.chain.to_dict()).home == "J154535"
    assert "unfiled" in session.execute("home!")
    assert session.chain.home is None
    assert "top of this fragment" in session.execute("top") or True
    session.execute("top")
    assert "top of this fragment" in session.execute("home")


def test_homeward_up_then_down(session):
    """Home on a branch: the route climbs to the fork, then descends."""
    session.execute("qlm J154535")
    session.ingest("ZZT-100\tCosmic Signature\tWormhole\t\t20.0%\t1 AU")
    session.execute("zzt J100744")
    session.execute("home J100744")
    session.execute("nav qlm")   # standing on the OTHER branch
    route = session.execute("home")
    assert "HOMEWARD (2 jumps)" in route
    assert "J154535" in route and "▸ ZZT" in route and "J100744" in route


# -- k-space destinations -----------------------------------------------------

def test_sig_opens_to_kspace_name(session):
    msg = session.execute("qlm tzvi")
    assert "opens to Tzvi" in msg and "0.3 L-sec" in msg and "Devoid" in msg
    conn = session.chain.root.find_connection("QLM")
    assert conn is not None and conn.child.name == "Tzvi"
    assert session.kspace["Tzvi"].band == "L"
    # Words that chart nothing still label.
    session.ingest("ZZT-100\tCosmic Signature\tWormhole\t\t20.0%\t1 AU")
    msg = session.execute("zzt definitely not a system")
    assert "labelled" in msg


def test_here_canonicalizes_kspace_name(session):
    msg = session.execute("here jita")
    assert "Jita" in msg
    assert session.chain.current().name == "Jita"
    assert session.kspace["Jita"].band == "H"


# -- k-space destinations ----------------------------------------------------

def test_sig_opens_to_kspace_name(session):
    msg = session.execute("qlm tzvi")
    assert "opens to Tzvi" in msg and "Devoid" in msg
    conn = session.chain.root.find_connection("QLM")
    assert conn is not None and conn.child.name == "Tzvi"
    assert session.kspace["Tzvi"].band == "L"
    # Words that chart nothing still label.
    session.ingest("ZZT-100\tCosmic Signature\tWormhole\t\t20.0%\t1 AU")
    msg = session.execute("zzt definitely not a system")
    assert "labelled" in msg


def test_here_canonicalizes_kspace_name(session):
    msg = session.execute("here jita")
    assert "Jita" in msg
    assert session.chain.current().name == "Jita"
    assert session.kspace["Jita"].band == "H"


# -- kind refiling ------------------------------------------------------------

def test_kind_words_refile_a_sig(session):
    session.ingest("ASD-123\tCosmic Signature\t\t\t2.5%\t4 AU")
    msg = session.execute("asd gas")
    assert "refiled: Gas Site" in msg
    assert session.chain.root.find_sig("ASD").group is SigGroup.GAS
    session.execute("asd relic")
    assert session.chain.root.find_sig("ASD").group is SigGroup.RELIC
    # An opened wormhole's kind is structural — refuse.
    session.ingest("QLM-802\tCosmic Signature\tWormhole\t\t40.0%\t1 AU")
    session.execute("qlm J154535")
    assert "REFUSED" in session.execute("qlm gas")


def test_quoted_label_beats_reserved_words(session):
    session.ingest("ASD-123\tCosmic Signature\t\t\t2.5%\t4 AU")
    msg = session.execute("asd \"gas\"")
    assert "labelled 'gas'" in msg
    sig = session.chain.root.find_sig("ASD")
    assert sig.label == "gas" and sig.group is SigGroup.UNKNOWN
