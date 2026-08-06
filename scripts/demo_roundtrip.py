"""M1 exit-criterion round-trip: paste → merge → open → nav → lazy → undo.

Run:  uv run python scripts/demo_roundtrip.py
"""

import sys
import tempfile
from pathlib import Path

# The editable-install .pth is unreliable here: iCloud marks .venv contents
# hidden under ~/Documents, and Python 3.11+ skips hidden .pth files.
sys.path.insert(0, str(Path(__file__).parent.parent))

from tuimapper.model.chain import Chain
from tuimapper.model.reconcile import apply_despawn, reconcile
from tuimapper.model.store import Store
from tuimapper.parsers.catalog import lookup_system, lookup_wh_type
from tuimapper.parsers.scanner import parse_scan

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"


def show(chain: Chain, indent: int = 0, system=None) -> None:
    system = system or chain.root
    here = " ◉ YOU" if system is chain.current() else ""
    info = f" [{system.jclass or '?'}{'/' + system.effect if system.effect else ''}]"
    print("  " * indent + f"{system.name}{info}{here}")
    for sig in system.sigs:
        conn = system.find_connection(sig.prefix)
        marker = "~" if conn else " "
        label = sig.label or sig.name or f"({sig.signal:.0f}%)"
        print("  " * (indent + 1) + f"{marker} {sig.prefix} {label}")
        if conn:
            show(chain, indent + 2, conn.child)


with tempfile.TemporaryDirectory() as tmp:
    store = Store(base_dir=Path(tmp))
    chain = Chain(name="demo")
    chain.root.name = "J105443"
    home = lookup_system(chain.root.name)
    chain.root.jclass, chain.root.effect = home.jclass, home.effect

    print("=== paste 1 (add) ===")
    report = reconcile(chain.current(), parse_scan((FIXTURES / "paste_mixed.txt").read_text()))
    store.commit(chain)
    print("new:", report.new)

    print("\n=== open QLM as a C1 static and jump in ===")
    dest = lookup_system("J154535")
    wh = lookup_wh_type(home.statics[0])
    chain.open_connection(
        "qlm", dest.jcode, jclass=dest.jclass, statics=dest.static_display,
        effect=dest.effect, wh_type=wh.code if wh else None,
    )
    chain.nav("qlm")
    store.commit(chain)
    chain.top()
    show(chain)

    print("\n=== paste 2 (lazy) at home ===")
    report = reconcile(
        chain.current(), parse_scan((FIXTURES / "paste_second.txt").read_text()), lazy=True
    )
    print("despawn candidates:", report.despawned, "blocked:", report.blocked)
    apply_despawn(chain.current(), report.despawned)
    store.commit(chain)
    show(chain)

    print("\n=== undo the lazy sweep ===")
    chain = store.undo("demo")
    show(chain)

print("\nround-trip OK")
