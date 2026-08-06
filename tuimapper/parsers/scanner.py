"""Parser for the EVE probe-scanner clipboard format.

Select-all + copy in the probe scanner yields tab-separated lines:

    ID<TAB>Scan Group<TAB>Group<TAB>Name<TAB>Signal<TAB>Distance

e.g.

    QLM-802	Cosmic Signature	Wormhole	Unstable Wormhole	100.0%	3.72 AU
    ASD-123	Cosmic Signature			0.0%	21.66 AU

Group and Name are empty until the sig is scanned far enough. We parse the
tabs — never character positions — and keep the signal strength.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tuimapper.model.chain import SigGroup

_SIG_ID = re.compile(r"^[A-Z]{3}-\d{3}$", re.IGNORECASE)

_GROUPS = {
    "wormhole": SigGroup.WORMHOLE,
    "unstable wormhole": SigGroup.WORMHOLE,
    "combat site": SigGroup.COMBAT,
    "data site": SigGroup.DATA,
    "relic site": SigGroup.RELIC,
    "gas site": SigGroup.GAS,
    "ore site": SigGroup.ORE,
}

COSMIC_SIGNATURE = "Cosmic Signature"


@dataclass(frozen=True)
class ScanLine:
    sig_id: str
    scan_group: str       # "Cosmic Signature", "Cosmic Anomaly", ...
    group: SigGroup
    name: str
    signal: float         # 0–100
    distance: str         # raw, e.g. "3.72 AU" / "4,015 km"

    @property
    def is_signature(self) -> bool:
        return self.scan_group == COSMIC_SIGNATURE


def _parse_signal(text: str) -> float:
    text = text.strip().rstrip("%").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_scan(text: str) -> list[ScanLine]:
    """Parse a probe-scanner paste. Unrecognisable lines are skipped."""
    lines: list[ScanLine] = []
    for raw in text.splitlines():
        fields = raw.rstrip("\r").split("\t")
        if len(fields) != 6:
            continue
        sig_id, scan_group, group, name, signal, distance = (f.strip() for f in fields)
        if not _SIG_ID.match(sig_id):
            continue
        lines.append(
            ScanLine(
                sig_id=sig_id.upper(),
                scan_group=scan_group,
                group=_GROUPS.get(group.lower(), SigGroup.UNKNOWN),
                name=name,
                signal=_parse_signal(signal),
                distance=distance,
            )
        )
    return lines
