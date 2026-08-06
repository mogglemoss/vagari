# tuimapper

> ANOIKIS CARTOGRAPHIC BUREAU · Department of Spatial Relations
> Ministry of Pantoscopic Observance · Chain Custody Instrument

A terminal wormhole chain mapper for EVE Online. Working title; final
designation pending review by the Ministry's Division of Nomenclature.

Single-pilot, local-state only. Clipboard paste is the only ingestion; no
login, no server, no ESI authentication. THE BUREAU MAKES NO REPRESENTATIONS
REGARDING THE PERSISTENCE OF SPACETIME.

## Running

```
uv run python -m tuimapper
```

(`python -m` rather than the console script: see the dev-env note in
[RESEARCH.md](RESEARCH.md).) Copy your probe scanner results (Ctrl+A, Ctrl+C)
and paste into the app. `?` inside the instrument shows the full reference.

## Status

M2 (TUI, feature parity with bashmapper and then some) complete — see
[PLAN.md](PLAN.md) for the milestone map: enrichment timers, then
chatlog-following, then packaged releases.

## Development

```
uv run pytest
uv run python scripts/demo_roundtrip.py
uv run python scripts/screenshot.py   # SVG screenshots via the test pilot
```

Interaction model inspired by [chloroken/bashmapper](https://github.com/chloroken/bashmapper).
Reference data derived from [anoik.is](https://anoik.is) — see
[tuimapper/data/ATTRIBUTION.md](tuimapper/data/ATTRIBUTION.md).
