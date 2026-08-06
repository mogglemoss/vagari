from datetime import datetime, timezone
from pathlib import Path

from vagari.model.chain import Signature, SigGroup, System
from vagari.model.reconcile import apply_despawn, reconcile
from vagari.parsers.scanner import parse_scan

FIXTURES = Path(__file__).parent / "fixtures"

T1 = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 8, 6, 13, 0, tzinfo=timezone.utc)


def paste(name: str):
    return parse_scan((FIXTURES / name).read_text())


def test_add_creates_sigs_and_skips_anomalies():
    system = System(name="J105443")
    report = reconcile(system, paste("paste_mixed.txt"), now=T1)
    assert report.new == ["ASD", "VMX", "FIY", "QLM"]  # XAL is an anomaly
    assert report.updated == []
    assert report.despawned == []
    assert {s.prefix for s in system.sigs} == {"ASD", "VMX", "FIY", "QLM"}
    assert all(s.first_seen == T1 for s in system.sigs)


def test_merge_only_improves():
    system = System(name="J105443")
    reconcile(system, paste("paste_mixed.txt"), now=T1)
    # Second paste: ASD now fully scanned, QLM unchanged, ZZT new.
    report = reconcile(system, paste("paste_second.txt"), now=T2)

    assert report.new == ["ZZT"]
    assert "ASD" in report.updated
    assert "QLM" not in report.updated  # nothing improved

    asd = system.find_sig("ASD")
    assert asd.group is SigGroup.DATA
    assert asd.name == "Unsecured Frontier Receiver"
    assert asd.signal == 100.0
    assert asd.first_seen == T1
    assert asd.last_seen == T2


def test_stale_paste_never_downgrades():
    system = System(name="J105443")
    reconcile(system, paste("paste_second.txt"), now=T1)  # ASD fully scanned
    reconcile(system, paste("paste_mixed.txt"), now=T2)   # ASD at 0.0% here

    asd = system.find_sig("ASD")
    assert asd.signal == 100.0
    assert asd.group is SigGroup.DATA
    assert asd.name == "Unsecured Frontier Receiver"


def test_user_label_survives_merge():
    system = System(name="J105443")
    reconcile(system, paste("paste_mixed.txt"), now=T1)
    system.find_sig("ASD").label = "my site"
    reconcile(system, paste("paste_second.txt"), now=T2)
    assert system.find_sig("ASD").label == "my site"


def test_lazy_reports_despawned_but_does_not_delete():
    system = System(name="J105443")
    reconcile(system, paste("paste_mixed.txt"), now=T1)
    report = reconcile(system, paste("paste_second.txt"), lazy=True, now=T2)

    assert set(report.despawned) == {"VMX", "FIY"}
    assert system.find_sig("VMX") is not None  # still there

    removed = apply_despawn(system, report.despawned)
    assert set(removed) == {"VMX", "FIY"}
    assert system.find_sig("VMX") is None


def test_lazy_blocks_connections_with_children():
    system = System(name="J105443")
    reconcile(system, paste("paste_mixed.txt"), now=T1)

    # Open FIY into a child that has mapped content.
    from vagari.model.chain import Connection

    child = System(name="J154535", sigs=[Signature(sig_id="AAA-111")])
    system.connections.append(Connection(sig_prefix="FIY", child=child))

    report = reconcile(system, paste("paste_second.txt"), lazy=True, now=T2)
    assert report.blocked == ["FIY"]
    assert report.despawned == ["VMX"]

    # A blocked prefix survives even an explicit sweep without force.
    removed = apply_despawn(system, ["FIY", "VMX"])
    assert removed == ["VMX"]
    assert system.find_sig("FIY") is not None
