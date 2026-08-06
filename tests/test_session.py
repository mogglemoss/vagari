from pathlib import Path

import pytest

from tuimapper.model.chain import MassState, SigGroup
from tuimapper.model.store import Store
from tuimapper.session import Session

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

    assert "REFUSED" in session.execute("del qlm")
    session.execute("del! qlm")
    assert session.chain.current().find_sig("QLM") is None


def test_lazy_and_sweep(session):
    session.execute("lazy")
    assert session.lazy_armed
    msg = session.ingest((FIXTURES / "paste_second.txt").read_text())
    assert "DESPAWNED" in msg and not session.lazy_armed
    session.execute("sweep")
    assert session.chain.current().find_sig("VMX") is None
    assert session.chain.current().find_sig("FIY") is None


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
    assert "J154535" in session.jump(["QLM"])
    assert session.chain.location == ["QLM"]


def test_unknown_command(session):
    assert "Unrecognised" in session.execute("frobnicate the chain")
