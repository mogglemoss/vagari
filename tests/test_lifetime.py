from datetime import datetime, timedelta, timezone

from tuimapper.model.chain import Connection, System
from tuimapper.model.lifetime import LifeStatus, assess, hours_text

T0 = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def conn(wh_type=None, eol=False, opened_hours_ago=0.0) -> Connection:
    return Connection(
        sig_prefix="QLM",
        child=System(name="J154535"),
        wh_type=wh_type,
        eol=eol,
        opened_at=T0 - timedelta(hours=opened_hours_ago),
    )


def test_untyped_connection_is_unknown():
    life = assess(conn(), now=T0)
    assert life.status is LifeStatus.UNKNOWN
    assert life.remaining_hours is None


def test_untyped_eol_still_reports_eol():
    assert assess(conn(eol=True), now=T0).status is LifeStatus.EOL


def test_healthy_countdown():
    # N110: 24h lifetime in the bundled catalog.
    life = assess(conn(wh_type="N110", opened_hours_ago=2), now=T0)
    assert life.status is LifeStatus.HEALTHY
    assert life.total_hours == 24.0
    assert abs(life.remaining_hours - 22.0) < 0.01


def test_waning_under_four_hours():
    life = assess(conn(wh_type="N110", opened_hours_ago=21), now=T0)
    assert life.status is LifeStatus.WANING


def test_expired_past_book_lifetime():
    life = assess(conn(wh_type="N110", opened_hours_ago=30), now=T0)
    assert life.status is LifeStatus.EXPIRED
    assert life.remaining_hours == 0.0


def test_eol_caps_remaining_at_four_hours():
    life = assess(conn(wh_type="N110", eol=True, opened_hours_ago=2), now=T0)
    assert life.status is LifeStatus.EOL
    assert life.remaining_hours == 4.0


def test_hours_text():
    assert hours_text(0.2) == "12m"
    assert hours_text(7.51) == "7h31m"
    assert hours_text(24) == "24h00m"
