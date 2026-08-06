"""Tiny text visualisations: gauges and sparklines."""

from __future__ import annotations

_BLOCKS = "▁▂▃▄▅▆▇█"


def gauge(fraction: float, cells: int = 6) -> str:
    """0.66, 6 → '▰▰▰▰▱▱'. Clamped."""
    fraction = max(0.0, min(1.0, fraction))
    filled = round(fraction * cells)
    return "▰" * filled + "▱" * (cells - filled)


def spark(values: list[int]) -> str:
    """[0, 1, 3, 8] → '▁▂▃█'. Empty input → ''."""
    if not values:
        return ""
    peak = max(values)
    if peak == 0:
        return _BLOCKS[0] * len(values)
    return "".join(
        _BLOCKS[min(len(_BLOCKS) - 1, round(v / peak * (len(_BLOCKS) - 1)))]
        for v in values
    )
