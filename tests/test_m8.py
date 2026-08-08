"""M8: search, k-space enrichment, zKill intel, OneDrive path."""

from pathlib import Path

import pytest

from vagari.enrichers.kspace import KSpaceInfo, pick_system_id
from vagari.enrichers.zkill import SystemKillStats, parse_system_stats
from vagari.followme.logtail import LOG_CANDIDATES
from vagari.model.store import Store
from vagari.session import Session

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def session(tmp_path):
    sess = Session.open(Store(base_dir=tmp_path / "state"))
    sess.chain.root.name = "J105443"
    sess.ingest((FIXTURES / "paste_mixed.txt").read_text())
    sess.execute("qlm J154535")
    sess.execute("fiy good relic")
    return sess


# -- search ------------------------------------------------------------------

def test_find_by_system_name(session):
    assert ("system", [0, "QLM"]) in session.find_matches("J1545")


def test_find_by_prefix_name_and_label(session):
    matches = session.find_matches("fiy")
    assert ("sig", [0], "FIY") in matches
    assert session.find_matches("good relic") == [("sig", [0], "FIY")]
    assert ("sig", [0], "FIY") in session.find_matches("crystal quarry")


def test_find_no_match_and_empty(session):
    assert session.find_matches("zzzzz") == []
    assert session.find_matches("  ") == []


# -- k-space -----------------------------------------------------------------

def test_pick_system_id_ignores_corps_and_alliances():
    payload = {
        "alliances": [{"id": 99005382, "name": "Jita Holding Inc."}],
        "systems": [{"id": 30000142, "name": "Jita"}],
    }
    assert pick_system_id(payload, "Jita") == 30000142
    assert pick_system_id(payload, "Amarr") is None
    assert pick_system_id({}, "Jita") is None


def test_kspace_bands_use_rounded_sec():
    jita = KSpaceInfo(30000142, 0.9459, "The Forge")
    assert jita.sec_display == "0.9" and jita.band == "H"
    # 0.45 rounds up to 0.5 → highsec, the classic trap.
    assert KSpaceInfo(1, 0.45, "X").band == "H"
    assert KSpaceInfo(1, 0.44, "X").band == "L"
    assert KSpaceInfo(1, 0.0, "X").band == "N"
    assert KSpaceInfo(1, -0.98, "X").band == "N"


def test_unresolved_kspace_names(session):
    assert session.unresolved_kspace_names() == []  # all J-space so far
    session.follow("Jita")
    session.file_k162()
    assert session.unresolved_kspace_names() == ["Jita"]
    session.kspace["Jita"] = KSpaceInfo(30000142, 0.9459, "The Forge")
    assert session.unresolved_kspace_names() == []


# -- zkill -------------------------------------------------------------------

def test_parse_system_stats():
    payload = {
        "shipsDestroyed": 1538343,
        "activepvp": {
            "characters": {"type": "Characters", "count": 795},
            "kills": {"type": "Total Kills", "count": 1354},
        },
    }
    stats = parse_system_stats(payload)
    assert stats == SystemKillStats(
        ships_destroyed=1538343, active_characters=795, active_kills=1354
    )
    assert parse_system_stats({}) == SystemKillStats(0, 0, 0)


# -- log path ----------------------------------------------------------------

def test_onedrive_candidate_present():
    assert any("OneDrive" in str(p) for p in LOG_CANDIDATES)
