from vagari.model.chain import SigGroup
from vagari.parsers.site_intel import classify_site, gas_contents


def test_ghost_site_is_timed():
    v = classify_site(SigGroup.DATA, "Guristas Covert Research Facility")
    assert v.label == "TIMED"
    assert v.hazard
    assert "detonates" in v.note


def test_sleeper_cache():
    v = classify_site(SigGroup.RELIC, "Superior Sleeper Cache")
    assert v.label == "CACHE"
    assert v.hazard
    assert "several hundred million" in v.worth
    lesser = classify_site(SigGroup.RELIC, "Standard Sleeper Cache")
    assert "deepest containers" in lesser.worth


def test_sleeper_guarded_sites_with_class_grade():
    relic = classify_site(SigGroup.RELIC, "Forgotten Core Data Field")
    assert relic.label == "GUARDED"
    assert "C5–C6 grade" in relic.note

    data = classify_site(SigGroup.DATA, "Unsecured Frontier Receiver")
    assert data.label == "GUARDED"
    assert "C3–C5 grade" in data.note


def test_gas_reservoir_tiers_and_contents():
    v = classify_site(SigGroup.GAS, "Vital Core Reservoir")
    assert v.label == "GAS"
    assert not v.hazard
    assert "richest clouds" in v.worth

    clouds = gas_contents("Vital Core Reservoir")
    assert [(c.gas, c.units) for c in clouds] == [
        ("Fullerite-C540", 24000),
        ("Fullerite-C320", 2000),
    ]
    # Client vs. legacy spelling both file correctly.
    assert gas_contents("Sizeable Perimeter Reservoir") == gas_contents(
        "Sizable Perimeter Reservoir"
    )
    assert gas_contents("Not A Reservoir") is None


def test_unguarded_pirate_tiers():
    ruined = classify_site(SigGroup.RELIC, "Ruined Sansha Crystal Quarry")
    assert ruined.label == "NO NPCS"
    assert "best containers" in ruined.note
    assert "Sansha space" in ruined.worth

    data = classify_site(SigGroup.DATA, "Central Guristas Data Mining Site")
    assert data.label == "NO NPCS"
    assert "blueprint lottery" in data.worth


def test_traps():
    assert classify_site(SigGroup.RELIC, "Sansha Observatory Infiltration").label == "TRAPPED"
    assert classify_site(SigGroup.DATA, "AEGIS Secure Transfer Facility").label == "ALARMED"


def test_combat_ore_wormhole_and_empty_say_nothing():
    assert classify_site(SigGroup.COMBAT, "Guristas Hideaway") is None
    assert classify_site(SigGroup.ORE, "Average Frontier Deposit") is None
    assert classify_site(SigGroup.WORMHOLE, "Unstable Wormhole") is None
    assert classify_site(SigGroup.DATA, "") is None
    assert classify_site(SigGroup.UNKNOWN, "Some Unrecognised Thing") is None
