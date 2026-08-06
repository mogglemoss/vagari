# tuimapper

> HARUSPEX CARTOGRAPHY DIVISION · Chain Custody Instrument · Capsuleer Edition

A terminal wormhole chain mapper for EVE Online. Working title; final
designation pending review by the Division of Nomenclature.

Single-pilot, local-state only. Clipboard paste is the only ingestion; no
login, no server, no ESI authentication. HARUSPEX MAKES NO REPRESENTATIONS
REGARDING THE PERSISTENCE OF SPACETIME.

## Status

M1 (engine, no UI) in progress — see [PLAN.md](PLAN.md).

## Development

```
uv run pytest
uv run python scripts/demo_roundtrip.py
```

Interaction model inspired by [chloroken/bashmapper](https://github.com/chloroken/bashmapper).
Reference data derived from [anoik.is](https://anoik.is) — see
[tuimapper/data/ATTRIBUTION.md](tuimapper/data/ATTRIBUTION.md).
