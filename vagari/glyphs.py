"""The Bureau's glyph vocabulary — UI-free so exports can use it too.

○ is a hole you can pass through — it pairs with the ◉ YOU marker. ◈/◇
pair relic (filled, treasure) with data (hollow, signal). ≈ is vapor, ▪ is
a chunk of rock, · is a signature not yet resolved. ▸ matches HARUSPEX's
combat glyph. All single-width geometrics: emoji render double-width in
some terminals and shear the tree.
"""

from __future__ import annotations

from vagari.model.chain import SigGroup

GLYPHS = {
    SigGroup.WORMHOLE: "○",
    SigGroup.COMBAT: "▸",
    SigGroup.DATA: "◇",
    SigGroup.RELIC: "◈",
    SigGroup.GAS: "≈",
    SigGroup.ORE: "▪",
    SigGroup.UNKNOWN: "·",
}

YOU = "◉ YOU"

_KIND_WORDS = {
    SigGroup.WORMHOLE: "WORMHOLE",
    SigGroup.COMBAT: "COMBAT",
    SigGroup.DATA: "DATA",
    SigGroup.RELIC: "RELIC",
    SigGroup.GAS: "GAS",
    SigGroup.ORE: "ORE",
    SigGroup.UNKNOWN: "UNFILED",
}

KIND_WIDTH = 8  # len("WORMHOLE")


def kind_word(group: SigGroup, name: str = "") -> str:
    """Filing kind for the tree's kind column. Ghost sites scan as data
    sites but file as GHOST — the distinction is safety-relevant."""
    if "covert research facility" in name.lower():
        return "GHOST"
    return _KIND_WORDS[group]
