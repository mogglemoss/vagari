"""Wormhole lifetime assessment.

`opened_at` records when the connection was first mapped, not when the hole
spawned, so remaining life is an upper bound — displayed as "≤Nh".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from vagari.model.chain import Connection, utcnow
from vagari.parsers.catalog import lookup_wh_type


class LifeStatus(str, Enum):
    UNKNOWN = "unknown"     # no wormhole type recorded
    HEALTHY = "healthy"
    WANING = "waning"       # under 4 hours of upper-bound life left
    EXPIRED = "expired"     # past its book lifetime; verify and sweep
    EOL = "eol"             # user marked end-of-life in game


WANING_HOURS = 4.0


@dataclass(frozen=True)
class Life:
    status: LifeStatus
    total_hours: float | None      # book lifetime for the type
    remaining_hours: float | None  # upper bound, clamped at 0


def assess(conn: Connection, now: datetime | None = None) -> Life:
    wh_type = lookup_wh_type(conn.wh_type) if conn.wh_type else None
    if wh_type is None or not wh_type.lifetime_hours:
        status = LifeStatus.EOL if conn.eol else LifeStatus.UNKNOWN
        return Life(status=status, total_hours=None, remaining_hours=None)

    total = float(wh_type.lifetime_hours)
    age = ((now or utcnow()) - conn.opened_at).total_seconds() / 3600
    remaining = max(0.0, total - age)

    if conn.eol:
        # In-game EOL means under ~4h regardless of our upper bound.
        return Life(LifeStatus.EOL, total, min(remaining, WANING_HOURS))
    if remaining <= 0:
        return Life(LifeStatus.EXPIRED, total, 0.0)
    if remaining < WANING_HOURS:
        return Life(LifeStatus.WANING, total, remaining)
    return Life(LifeStatus.HEALTHY, total, remaining)


def hours_text(hours: float) -> str:
    """7.51 → '7h31m'; 0.2 → '12m'."""
    minutes = int(round(hours * 60))
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h{minutes % 60:02d}m"
