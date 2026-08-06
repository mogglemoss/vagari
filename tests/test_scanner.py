from pathlib import Path

from vagari.model.chain import SigGroup
from vagari.parsers.scanner import parse_scan

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_parses_all_valid_lines():
    lines = parse_scan(load("paste_mixed.txt"))
    assert [l.sig_id for l in lines] == [
        "ASD-123",
        "VMX-171",
        "FIY-570",
        "QLM-802",
        "XAL-201",
    ]


def test_unscanned_sig_has_no_group_or_name():
    line = parse_scan(load("paste_mixed.txt"))[0]
    assert line.group is SigGroup.UNKNOWN
    assert line.name == ""
    assert line.signal == 0.0
    assert line.is_signature


def test_partial_scan_keeps_signal_and_group():
    line = parse_scan(load("paste_mixed.txt"))[1]
    assert line.group is SigGroup.GAS
    assert line.signal == 87.5
    assert line.name == ""


def test_full_scan():
    relic, wh = parse_scan(load("paste_mixed.txt"))[2:4]
    assert relic.group is SigGroup.RELIC
    assert relic.name == "Ruined Guristas Crystal Quarry"
    assert relic.signal == 100.0
    assert wh.group is SigGroup.WORMHOLE


def test_anomaly_is_not_a_signature():
    anomaly = parse_scan(load("paste_mixed.txt"))[4]
    assert anomaly.scan_group == "Cosmic Anomaly"
    assert not anomaly.is_signature


def test_garbage_lines_skipped():
    assert parse_scan("hello\nworld\t\t\t\t\t\n") == []
    assert parse_scan("") == []


def test_comma_decimal_signal():
    text = "ABC-001\tCosmic Signature\t\t\t12,5%\t1 AU"
    assert parse_scan(text)[0].signal == 12.5


def test_lowercase_id_normalised():
    text = "abc-001\tCosmic Signature\t\t\t0.0%\t1 AU"
    assert parse_scan(text)[0].sig_id == "ABC-001"
