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
    t = now or utcnow()

    # A filed in-game reading is authoritative over the book estimate.
    if conn.life_seen == "expired":
        total = float(wh_type.lifetime_hours) if wh_type and wh_type.lifetime_hours else None
        return Life(LifeStatus.EXPIRED, total, 0.0)
    seen_cap = None
    if conn.life_seen == "waning" and conn.life_seen_at is not None:
        seen_cap = 24.0 - (t - conn.life_seen_at).total_seconds() / 3600
        if seen_cap <= 0:
            return Life(LifeStatus.EXPIRED, None, 0.0)
    seen_floor = None
    if conn.life_seen == "day" and conn.life_seen_at is not None:
        seen_floor = 24.0 - (t - conn.life_seen_at).total_seconds() / 3600

    if wh_type is None or not wh_type.lifetime_hours:
        if conn.eol:
            # Untyped holes (K162s) still get the 4h clock from marking.
            caps = [WANING_HOURS]
            if conn.eol_marked_at is not None:
                caps.append(WANING_HOURS - (
                    (t - conn.eol_marked_at).total_seconds() / 3600
                ))
            if conn.life_seen == "hour" and conn.life_seen_at is not None:
                caps.append(
                    1.0 - (t - conn.life_seen_at).total_seconds() / 3600
                )
            return Life(LifeStatus.EOL, None, max(0.0, min(caps)))
        if seen_cap is not None:
            status = (
                LifeStatus.WANING if seen_cap < WANING_HOURS
                else LifeStatus.HEALTHY
            )
            return Life(status, None, seen_cap)
        return Life(LifeStatus.UNKNOWN, None, None)

    total = float(wh_type.lifetime_hours)
    age = (t - conn.opened_at).total_seconds() / 3600
    remaining = max(0.0, total - age)
    if seen_cap is not None:
        remaining = min(remaining, seen_cap)
    if seen_floor is not None and seen_floor > 0:
        # The pilot read "at least another day" — the book estimate cannot
        # undercut what the game itself declared.
        remaining = max(remaining, seen_floor)

    if conn.eol:
        # In-game EOL means under ~4h from the moment it was NOTICED —
        # count down from the marking, bounded by the book estimate. A
        # filed "less than 1 hour" reading tightens the cap further.
        caps = [remaining]
        if conn.eol_marked_at is not None:
            caps.append(WANING_HOURS - (
                (t - conn.eol_marked_at).total_seconds() / 3600
            ))
        else:
            caps.append(WANING_HOURS)
        if conn.life_seen == "hour" and conn.life_seen_at is not None:
            caps.append(1.0 - (t - conn.life_seen_at).total_seconds() / 3600)
        return Life(LifeStatus.EOL, total, max(0.0, min(caps)))
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
