"""The command registry — one source of truth for the reference screen,
the palette, and the suggester. A command defined here appears everywhere,
consistently, or nowhere.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    name: str            # canonical first word ("" for paste)
    grammar: str         # how it is written
    help: str            # one filing line
    category: str
    keys: str = ""       # instant key(s), if any
    palette: str = ""    # palette title ("" = not in the palette)
    action: str = ""     # app action the palette invokes
    aliases: tuple[str, ...] = ()


CATEGORIES = [
    ("drive", "how to drive it"),
    ("scanning", "scanning"),
    ("navigation", "navigation"),
    ("record", "the record"),
    ("forest", "the forest"),
    ("views", "views & custody"),
    ("follow", "follow-me"),
    ("meta", "the instrument"),
]

REGISTRY: list[Command] = [
    # drive (rendered from the reference screen's extra pairs)
    # scanning
    Command("", "paste", "file scan results — new sigs are added, sigs "
            "missing from a fresh scan are reported as despawn candidates; "
            "nothing is deleted", "scanning"),
    Command("sweep", "sweep", "strike every reported despawn (collapsed "
            "holes with children sever)", "scanning", keys="s",
            palette="Sweep despawned", action="sweep"),
    # navigation
    Command("nav", "nav abc …", "proceed through wormhole ABC", "navigation"),
    Command("up", "up", "return toward the fragment root", "navigation",
            keys="u"),
    Command("top", "top", "return to the fragment root", "navigation",
            keys="g", palette="Return to root", action="go_top"),
    Command("home", "home", "retrace the route to the root, door by door",
            "navigation", keys="h", palette="Homeward",
            action="show_homeward", aliases=("route",)),
    Command("", "y", "cursor to ◉ YOU", "navigation", keys="y"),
    # the record
    Command("", "abc J105443", "open ABC to a system — J-code or k-space "
            "name (abc tzvi); a fragment's name adopts it", "record"),
    Command("", "abc H296", "type wormhole ABC — class, lifetime, mass",
            "record"),
    Command("", "abc <words>", "label a signature (quote a reserved "
            "word: abc \u2018gas\u2019)", "record"),
    Command("", "abc gas", "refile a sig's kind — wormhole · combat · "
            "data · relic · gas · ore", "record"),
    Command("return", "return abc [B274]", "abc is the way home; optional "
            "type read from this side (re-pair to correct; return! unpairs)",
            "record", aliases=("return!",)),
    Command("here", "here <name>", "name the current system", "record"),
    Command("flag", "flag abc", "flag a signature for attention", "record",
            keys="x"),
    Command("strike", "strike abc · strike vard · strike #2",
            "expunge a sig, system, or fragment from the record (strike! "
            "forces; del and discard are the same verb, older spellings)",
            "record", keys="d", aliases=("del", "del!", "discard", "discard!",
                                         "strike!")),
    Command("eol", "eol abc", "toggle end-of-life; the 4h clock runs from "
            "the marking", "record", keys="e"),
    Command("life", "life abc >24 · <24 · <4 · <1 · gone", "file the "
            "in-game lifetime reading as observed", "record"),
    Command("crit", "crit abc [>50 · <50 · <10]", "cycle mass — or file "
            "the in-game reading directly", "record", keys="m",
            aliases=("mass",)),
    Command("rekey", "zaa = abc", "refile a hole under its real sig — "
            "moves the connection; a mis-picked real sig survives, "
            "unopened", "record"),
    Command("cull", "cull", "strike every hole past its book lifetime "
            "(children sever)", "record", palette="Cull expired",
            action="cull"),
    Command("", "… @system", "address a sig elsewhere; otherwise current "
            "system first, then unique anywhere", "record"),
    Command("", "(the dossier)", "its filing field and action links accept "
            "this same grammar, pre-addressed to the selection", "record"),
    # the forest
    Command("sever", "sever abc", "the opposite of strike: cut the hole "
            "but KEEP the far side as an adrift fragment", "forest"),
    Command("fragment", "fragment [name]", "file a disconnected fragment "
            "(or a pending arrival)", "forest"),
    Command("k162", "k162", "arrivals file themselves as you jump; k162 "
            "hand-files a queued one in the rare case one is pending",
            "forest", keys="k", palette="File K162",
            action="file_k162", aliases=("k", "k162!", "k!")),
    # views & custody
    Command("", "1–5", "all · paths · sites · gas · combat (structural "
            "wormholes stay)", "views"),
    Command("undo", "undo / redo", "the record, backward and forward, "
            "without limit", "views", keys="z Z",
            palette="Undo", action="undo"),
    Command("chain", "chain <name>", "switch chain of custody", "views"),
    Command("copy", "copy · copy route", "chain, or the route home, to the "
            "clipboard", "views", keys="c", palette="Copy chain",
            action="copy_chain"),
    Command("/", "/query", "find a system, sig, or label; repeat to cycle",
            "views", keys="/", palette="Find", action="start_search"),
    # follow-me
    Command("pilot", "pilot [name|off]", "who follow-me follows; first to "
            "jump otherwise", "follow"),
    Command("recon", "recon", "refresh the picture: last-hour activity "
            "for every system (watchtower alerts) + killboard for the "
            "system on display", "follow", palette="Recon: refresh "
            "activity", action="recon", aliases=("intel",)),
    # meta ("Tab / :" lives under "how to drive it" on the reference screen)
    Command("", "?", "this reference", "meta", keys="?",
            palette="Reference", action="show_help"),
    Command("", "a", "about — the instrument's papers", "meta", keys="a",
            palette="About", action="show_about"),
    Command("", "q", "quit", "meta", keys="q", palette="Quit",
            action="quit"),
]


def first_words() -> list[str]:
    """Command words for the suggester, canonical names first."""
    words: list[str] = []
    for c in REGISTRY:
        if c.name and c.name not in words and c.name != "/":
            words.append(c.name)
    for c in REGISTRY:
        for a in c.aliases:
            if a not in words:
                words.append(a)
    return words
