"""Render the app with a demo chain and export SVG screenshots.

Run:  uv run python scripts/screenshot.py [outdir]
"""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from textual import events

from vagari.main import MapperApp
from vagari.model.store import Store
from vagari.session import Session

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")


def build_session(tmp: Path) -> Session:
    session = Session.open(Store(base_dir=tmp))
    session.chain.root.name = "J105443"
    session.ingest((FIXTURES / "paste_mixed.txt").read_text())
    session.execute("qlm J154535")
    session.execute("fiy sleeper cache — good loot")
    session.execute("flag asd")
    session.execute("nav qlm")
    session.ingest((FIXTURES / "paste_second.txt").read_text())
    session.execute("asd J164417")
    session.execute("qlm N110")
    session.execute("eol qlm")
    session.execute("crit qlm")
    session.execute("nav asd")
    session.ingest(
        "KWV-100\tCosmic Signature\tWormhole\tUnstable Wormhole\t100.0%\t1.2 AU\n"
        "PXA-200\tCosmic Signature\tGas Site\tOrdinary Perimeter Reservoir\t100.0%\t8.8 AU\n"
        "RRB-300\tCosmic Signature\t\t\t34.2%\t19.0 AU\n"
    )
    session.execute("kwv K162")

    # Backdate the N110 so the lifetime countdown shows a waning hole,
    # and file some reconnaissance so the detail panel has activity data.
    from datetime import timedelta

    from vagari.enrichers.activity import SystemActivity
    from vagari.parsers.catalog import lookup_system

    session.chain.top()
    session.execute("nav qlm")
    n110 = session.chain.current().find_connection("QLM")
    n110.opened_at -= timedelta(hours=21, minutes=30)
    session.chain.top()
    session.activity = {
        lookup_system("J164417").system_id: SystemActivity(3, 1, 12),
        lookup_system("J154535").system_id: SystemActivity(0, 0, 44),
    }
    session.activity_fetched = True
    return session


async def shoot() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        session = build_session(Path(tmp))
        app = MapperApp(session=session, recon=False)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            app.save_screenshot(str(OUT / "shot_chain.svg"))
            await pilot.press("down", "down", "down", "down")
            await pilot.pause()
            app.save_screenshot(str(OUT / "shot_detail.svg"))
            await pilot.press("question_mark")
            await pilot.pause()
            app.save_screenshot(str(OUT / "shot_help.svg"))
    for name in ("shot_chain", "shot_detail", "shot_help"):
        path = OUT / f"{name}.svg"
        # rsvg-convert renders &#160; as zero-width when the font falls back;
        # real spaces + xml:space="preserve" convert faithfully.
        svg = path.read_text().replace("&#160;", " ")
        svg = svg.replace("<text ", '<text xml:space="preserve" ')
        path.write_text(svg)
    print("saved to", OUT)


if __name__ == "__main__":
    asyncio.run(shoot())
