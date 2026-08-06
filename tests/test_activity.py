from vagari.enrichers.activity import SystemActivity, parse_system_kills


def test_parse_payload():
    payload = [
        {"system_id": 31002604, "ship_kills": 2, "pod_kills": 1, "npc_kills": 40},
        {"system_id": 30000142, "npc_kills": 7},
    ]
    activity = parse_system_kills(payload)
    assert activity[31002604] == SystemActivity(ship_kills=2, pod_kills=1, npc_kills=40)
    assert activity[30000142] == SystemActivity(ship_kills=0, pod_kills=0, npc_kills=7)


def test_hostile_flag():
    assert SystemActivity(1, 0, 0).hostile
    assert SystemActivity(0, 1, 0).hostile
    assert not SystemActivity(0, 0, 99).hostile


def test_parse_skips_malformed_rows():
    payload = [
        {"ship_kills": 2},                       # no system_id
        {"system_id": "not-a-number-x"},
        {"system_id": 30000142, "ship_kills": 1},
    ]
    activity = parse_system_kills(payload)
    assert list(activity) == [30000142]
