# vagari — Research Notes

Research date: 2026-08-06. Sources: chloroken/bashmapper (read in full), the local
HARUSPEX codebase (surveyed), and the local eve-online-spookyspace data pipeline.

## eve-online-spookyspace reference data (supersedes bashmapper data.txt)

`../eve-online-spookyspace/src/data/` holds anoik.is-derived JSON (ingest pipeline in
`../eve-online-spookyspace/ingest/`; `meta.json` records source URL/version/date):

- `systems.json` — 2,604 J-space systems: `{id, systemId, name, classKey, effect,
  region, constellation, shattered, statics: [type codes], sun, planets, ...}`.
  classKey vocab: c1–c6, c13, thera, barbican/conflux/redoubt/sentinel/vidette (drifter).
- `wormhole_types.json` — 90 types: `{code, targetClass, sourceClasses, isStatic,
  totalMass, jumpMass, lifetimeHours, massRegen, size, typeId}`. targetClass includes
  hs/ls/ns and null (K162-style).
- `effects.json` — weather bonus tables by class; `classes.json` — class metadata.

Vendored into `vagari/data/` (M1). This resolves the wormhole-type DB need for M3
lifetime/mass estimates.

## Naming family

GitHub org `mogglemoss`: HARUSPEX (d-scan TUI), AUSPEX (Android char intel),
RETROSPEX (pilot dossier, killboard-driven, private repo — richer killboard patterns
than haruspex's zkill.py; consult for M3). Convention: Latin **-SPEX**, "one who
observes". vagari's final name should follow it.

## Dev-env gotcha (verified 2026-08-06)

iCloud syncs `~/Documents`; a background process applies macOS `UF_HIDDEN` to `.venv`
contents (re-applies within minutes of clearing), and Python 3.11+ `site.addpackage`
silently skips hidden `.pth` files → editable installs break outside the project root.
Diagnose with `ls -lO .venv/lib/python*/site-packages/*.pth`. Mitigation: repo scripts
and `tests/conftest.py` insert the project root into `sys.path` themselves.

## bashmapper (github.com/chloroken/bashmapper, MIT)

~250-line bash script + 2,605-line static catalog. Three files total: `map.sh`, `data.txt`,
`README.md`. Linux + Wayland only (`wl-clipboard`). 3 stars, single author, self-described
as under development; author comments flag the parsing section for "complete refactor".

### The core conceit
The wormhole chain **is a directory tree**. One directory per signature; nesting = chain
topology; `$PWD` = current system; `tree -C` = renderer; `cd` = navigation; `mv` = rename;
undo = three rotating full copies of the tree (`undo1/ undo2/ undo3/`).

### Command surface (the interaction model worth preserving)
- `map add` — paste sigs from clipboard, merge additively
- `map lazy` — paste + flag sigs missing from clipboard for deletion ("lazy delete")
- `map undo` — 3-step undo
- `map up` / `map top` / `map nav <sig> <sig>..` — navigate the chain
- `map full` / `map paths` / `map gas` — filtered views (all / wormholes / wormholes+gas)
- `map <sig> <label>` — rename; `map <sig> <jcode>` — auto-label from data.txt
- `map flag <sig>..` — append `!` to a sig
- `map del <sig>..` — delete sigs

Every command addresses sigs by their **three-letter prefix** (`ABC-123` → `abc`).

### Ingestion pipeline
`wl-paste` → whitespace normalization → per line: keep chars 1–3 (sig prefix) and 9+
(name), trim at first digit, then a wall of `sed` substitutions that delete site-name
noise ("Perimeter Amplifier", "Frontier Trinary Hub", …) and rewrite categories to glyph
markers: `—Data—`, `—Relic—`, `—Combat—`, `~` = wormhole, `<` = gas reservoir.
Merge heuristic on re-paste: **keep whichever label string is longer** (more-scanned sigs
have longer names — "somehow this actually works").

### data.txt (the crown-jewel asset)
Format: `~ J154535 ~ C1+N ~ Black Hole` — J-code, class + static (`C2+3,H` = C2 with
C3 and highsec statics; `N`/`L`/`H` = null/low/high), optional weather effect (Black Hole,
Pulsar, Magnetar, Wolf-Rayet, Cataclysmic Variable, Red Giant). Covers all ~2,600 J-space
systems, C1–C6. **Statics and effects are not cleanly available from ESI** — this file is
the hardest data in the repo to reproduce. MIT-licensed → vendor with attribution.

### Deliberately absent (and we keep it that way)
No ESI auth, no server, no browser, no multi-user. Clipboard is the entire sync protocol.

### Its actual limitations (why from-scratch, not fork)
Wayland-only clipboard; single chain; no timestamps → no EOL/lifetime tracking; fixed
char-position parsing breaks on format drift; state is directory names (spaces, `!`, `<`
in dirnames); no scan-strength awareness; sh-level error handling.

## HARUSPEX (local: ../haruspex) — the sibling to copy from

Python 3.11 + **Textual** ≥8.1.1 + httpx; hatchling + uv; ~3,000 LOC, 15 modules.
PyInstaller `--onedir` (onefile breaks Textual key input on Linux — hard-won), universal2
on macOS, 3-platform GitHub Actions release matrix on `v*` tags.

Directly liftable, in value order:
1. `haruspex/enrichers/esi.py` — bulk public-ESI resolution (names→IDs→affiliations→
   corp/alliance), chunked, `Semaphore(10)`, no auth coupling.
2. `haruspex/config/settings.py` — dataclass + TOML config with defaults fallback, plus
   cross-platform EVE log path detection (macOS / Steam Proton / Flatpak).
   Known wart: duplicate macOS path in `_LOG_CANDIDATES`.
3. `haruspex.spec` + `.github/workflows/build.yml` — the whole release pipeline.
4. Theme: `main.py:25-131` — complete Textual de-blue-ing CSS, warm dark palette
   (accent `#C15F3C`, bg `#1a1815`, text `#e8e6e3`, border `#3a3530`). Inline in
   `App.CSS`; extract to `.tcss` when copying.
5. `haruspex/parsers/logs.py` — async UTF-16LE chatlog tailer with rotation handling and
   system-change detection (basis for map-follows-you).
6. `haruspex/enrichers/zkill.py` — rate-limited zKill client + WH corp/alliance flag lists.
7. `scripts/build_ships.py` — pattern for regenerating bundled static data from ESI.
   Known wart: writes to stale `lazyscan/` path.

Voice: deadpan corporate intelligence bureaucracy, third person, ALL-CAPS legal
boilerplate in empty states, clinical euphemisms ("Deposit scan telemetry"), org-unit
naming per panel (INTELLIGENCE / PERSONNEL / MONITORING DIVISION), British spelling,
box-drawing mascot with animated accent. vagari = **CARTOGRAPHY DIVISION**.

## Probe scanner clipboard format (target of the new parser)

Ctrl-A/Ctrl-C in the probe scanner yields tab-separated lines:
`ID<TAB>Group<TAB>Name<TAB>Signal<TAB>Distance`, e.g.
`ABC-123	Cosmic Signature	Wormhole	100.0%	4.21 AU`
Partially scanned sigs have empty/generic Group/Name and signal < 100%. Parse the tabs,
not character positions; keep the signal % (bashmapper throws it away).
