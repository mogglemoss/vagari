from tuimapper.parsers.catalog import lookup_system, lookup_wh_type, load_systems


def test_catalog_loads_all_jspace():
    systems = load_systems()
    assert len(systems) > 2500


def test_plain_c1():
    info = lookup_system("J105443")
    assert info is not None
    assert info.jclass == "C1"
    assert info.effect is None
    assert not info.shattered
    assert info.static_display == "N"


def test_effect_system():
    info = lookup_system("J154535")
    assert info is not None
    assert info.jclass == "C1"
    assert info.effect == "Black Hole"


def test_multi_static():
    info = lookup_system("J164417")
    assert info is not None
    assert info.jclass == "C2"
    assert set(info.static_display.split(",")) == {"C3", "H"}


def test_shattered_c13():
    info = lookup_system("J000102")
    assert info is not None
    assert info.jclass == "C13"
    assert info.shattered


def test_lookup_variants():
    assert lookup_system("j105443") is not None
    assert lookup_system("105443") is not None
    assert lookup_system("J999999") is None


def test_wormhole_types():
    n110 = lookup_wh_type("N110")
    assert n110 is not None
    assert n110.target_display == "H"
    assert n110.lifetime_hours > 0
    assert n110.jump_mass > 0
    assert lookup_wh_type("XYZ9") is None
