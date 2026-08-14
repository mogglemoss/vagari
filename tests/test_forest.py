"""M9: the forest — fragments, severing, adoption, migration."""

import json
from pathlib import Path

import pytest

from vagari.model.chain import Chain
from vagari.model.store import Store
from vagari.session import Session

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def session(tmp_path):
    sess = Session.open(Store(base_dir=tmp_path / "state"))
    sess.chain.root.name = "J105443"
    sess.ingest((FIXTURES / "paste_mixed.txt").read_text())
    sess.execute("qlm J154535")
    sess.execute("nav qlm")
    sess.ingest((FIXTURES / "paste_second.txt").read_text())
    sess.execute("top")
    return sess


def test_sever_creates_fragment(session):
    msg = session.execute("sever qlm")
    assert "severed" in msg and "fragment #2" in msg
    assert len(session.chain.roots) == 2
    assert session.chain.roots[1].name == "J154535"
    assert session.chain.roots[1].find_sig("ZZT") is not None
    assert session.chain.root.find_sig("QLM") is None


def test_sever_while_inside_moves_you_to_fragment(session):
    session.execute("nav qlm")
    # QLM exists as a sig prefix in both systems (fixture collision) — the
    # @qualifier addresses the opened hole in the parent.
    session.execute("sever qlm @J105443")   # the hole home collapses behind us
    assert session.chain.location == [1]
    assert session.chain.current().name == "J154535"
    # Navigation within the fragment still works.
    assert "top of this fragment" in session.homeward()


def test_sweep_severs_despawned_hole_with_children(session):
    # A paste WITHOUT the QLM hole: it despawned while its far side is mapped.
    session.ingest(
        "ASD-123\tCosmic Signature\tData Site\tUnsecured Frontier Receiver\t100.0%\t1 AU"
    )
    msg = session.execute("sweep")
    assert "severed" in msg
    assert len(session.chain.roots) == 2
    assert session.chain.roots[1].name == "J154535"


def test_arrival_never_lingers_for_fragment(session):
    session.follow("J100744")               # files itself on arrival
    assert session.pending_arrival is None
    assert session.chain.current().name == "J100744"
    assert session.chain.current().jclass == "C1"  # catalog-enriched


def test_fragment_by_name(session):
    msg = session.execute("fragment J100744")
    assert "fragment #2" in msg
    assert session.chain.current().name == "J100744"


def test_adoption_reattaches_fragment(session):
    session.execute("sever qlm")            # J154535 adrift as fragment #2
    session.execute("top")
    # Later we scan a fresh hole in the root and identify its destination
    # as the adrift fragment: opening to it adopts instead of duplicating.
    session.ingest("NEW-001\tCosmic Signature\tWormhole\t\t60.0%\t1 AU")
    msg = session.execute("new J154535")
    assert "reattached" in msg
    assert len(session.chain.roots) == 1
    conn = session.chain.root.find_connection("NEW")
    assert conn is not None and conn.child.name == "J154535"
    assert conn.child.find_sig("ZZT") is not None  # subtree intact


def test_adoption_from_inside_fragment_remaps_location(session):
    session.execute("sever qlm")
    session.execute("nav" if False else "fragment J100744")  # place YOU in a 3rd fragment
    # Stand inside the adrift J154535 fragment instead.
    session.chain.location = [1]
    session.execute("top")
    assert session.chain.current().name == "J154535"
    session.ingest("NEW-001\tCosmic Signature\tWormhole\t\t60.0%\t1 AU @J105443"
                   .replace(" @J105443", ""))
    # Open from the ROOT fragment side, addressing the sig remotely.
    session.chain.location = [0]
    session.ingest("NEW-001\tCosmic Signature\tWormhole\t\t60.0%\t1 AU")
    session.chain.location = [1]            # we are inside the fragment
    session.execute("new J154535 @J105443")
    assert session.chain.location[:2] == [0, "NEW"]
    assert session.chain.current().name == "J154535"


def test_adoption_refuses_own_fragment(session):
    session.execute("nav qlm")
    # ZZT is in J154535; opening it "to J105443"? — fine. But opening a sig
    # to the very fragment containing it must refuse (would close a loop).
    session.execute("top")
    session.ingest("NEW-001\tCosmic Signature\tWormhole\t\t60.0%\t1 AU")
    msg = session.execute("new J105443")
    assert "REFUSED" in msg and "loop" in msg


def test_legacy_snapshot_migrates(tmp_path):
    legacy = {
        "name": "home",
        "root": {
            "name": "J105443", "jclass": "C1", "statics": "N", "effect": None,
            "sigs": [], "connections": [],
        },
        "location": [],
    }
    chain = Chain.from_dict(legacy)
    assert chain.roots[0].name == "J105443"
    assert chain.location == [0]
    # And the new format round-trips.
    again = Chain.from_dict(chain.to_dict())
    assert again.location == [0] and len(again.roots) == 1


def test_export_lists_fragments(session):
    from vagari.export import export_text

    session.execute("sever qlm")
    text = export_text(session.chain)
    assert "fragment #2, adrift" in text
    assert "J154535" in text


def test_adopt_kspace_fragment_by_name(session):
    session.execute("fragment Vard")
    session.chain.location = [0]
    session.ingest("SYQ-001\tCosmic Signature\tWormhole\t\t80.0%\t1 AU")
    msg = session.execute("syq vard")
    assert "reattached" in msg
    conn = session.chain.root.find_connection("SYQ")
    assert conn is not None and conn.child.name == "Vard"
    assert conn.child.adrift_since is None
    assert len(session.chain.roots) == 1
    # A single token that matches nothing still labels, as before.
    session.ingest("LBL-001\tCosmic Signature\tGas Site\t\t50.0%\t1 AU")
    session.execute("lbl mine")
    assert session.chain.root.find_sig("LBL").label == "mine"


def test_flying_into_fragment_reattaches(session):
    session.execute("fragment J141150")
    session.chain.location = [0]
    session.ingest("HUV-001\tCosmic Signature\tWormhole\tUnstable Wormhole\t100.0%\t1 AU")
    session.execute("huv U210")            # HUV → "?"
    msg = session.follow("J141150")        # jump: arrival IS the fragment
    assert "reattached" in msg and "HUV" in msg
    assert len(session.chain.roots) == 1
    conn = session.chain.root.find_connection("HUV")
    assert conn.child.name == "J141150"
    assert session.chain.current().name == "J141150"
