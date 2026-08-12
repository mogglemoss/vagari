# VAGARI — Plan

Named **VAGARI** (Latin *vagari*, "to wander") on 2026-08-06 — a deliberate departure
from the -SPEX family, keeping the Ministry's Latin register with a nomadic cast.
In-fiction: an instrument of the **Anoikis Cartographic Bureau, Department of Spatial
Relations, Ministry of Pantoscopic Observance**.

> Status 2026-08-06: **M1 complete** — engine (model/store/reconcile/parsers) built and
> tested, 34 tests green, round-trip demo (`scripts/demo_roundtrip.py`) passing.
> Reference data switched from bashmapper's data.txt to spookyspace's anoik.is-derived
> JSONs (see RESEARCH.md), which also resolves the M3 wormhole-type-DB risk item.

## Locked decisions

- **From scratch, inspired by bashmapper** (interaction model preserved, zero code or
  data reused — reference data comes from spookyspace's anoik.is ingest instead).
- **Standalone binary**, sibling to HARUSPEX — not a HARUSPEX panel.
- **Single-pilot, local-state only.** No server, no ESI auth, no multi-user. Clipboard
  paste is the only ingestion; public ESI/zKill only for optional enrichment.
- Python 3.11 + Textual + httpx; uv + hatchling; PyInstaller `--onedir`; same 3-platform
  release CI as HARUSPEX.

## Design laws (inherited from bashmapper)

1. Paste is the source of truth — the tool reconciles against it, never fights it.
2. Sigs are addressed by three-letter prefix, always case-insensitive.
3. Keystrokes are precious: common operations ≤ one short command or one key.
4. The chain renders as a tree. Filtered views: full / wormholes / wormholes+gas.

## Architecture

```
vagari/
  pyproject.toml            # uv + hatchling, console script vagari=vagari.main:main
  vagari.spec            # PyInstaller --onedir, universal2 (copy haruspex.spec)
  .github/workflows/build.yml
  vagari/
    main.py                 # App shell, keybindings, theme import
    theme.tcss              # HARUSPEX palette, extracted (not inline CSS)
    model/
      chain.py              # Chain / System / Signature / Connection dataclasses
      store.py              # snapshot persistence + undo/redo
      reconcile.py          # paste-merge logic (add / lazy semantics)
    parsers/
      scanner.py            # probe-scanner clipboard parser (tab-based)
      catalog.py            # systems/wormhole-types loader (SystemInfo, WormholeType)
    enrichers/              # copied from HARUSPEX, trimmed
      esi.py
      zkill.py
    followme/
      logtail.py            # chatlog tailer (from haruspex parsers/logs.py) — M4
    ui/
      chain_tree.py         # Textual Tree of the chain
      detail_panel.py       # selected system/sig detail
      command_bar.py        # bashmapper-grammar command input
      widgets.py            # header, paste handling, mascot
      help_screen.py
    data/
      systems.json          # + wormhole_types.json, effects.json, meta.json
                            # (anoik.is via spookyspace ingest; see ATTRIBUTION.md)
  tests/
    test_scanner.py         # fixture-driven, like haruspex test_dscan
    test_reconcile.py
    test_store.py
```

### Data model (the real upgrade over a directory tree)

```python
@dataclass
class Signature:
    sig_id: str            # "ABC-123"; prefix = sig_id[:3].upper()
    group: SigGroup        # WORMHOLE | COMBAT | DATA | RELIC | GAS | ORE | UNKNOWN
    name: str              # site name if fully scanned, else ""
    signal: float          # scan strength 0–100
    label: str             # user label
    flagged: bool          # bashmapper's "!"
    first_seen: datetime
    last_seen: datetime

@dataclass
class Connection:          # a wormhole sig that has been "opened"
    sig: Signature
    child: System
    wh_type: str | None    # "K162", "H296", ...
    eol: bool              # user-marked end-of-life
    mass: MassState        # FRESH | REDUCED | CRITICAL
    opened_at: datetime

@dataclass
class System:
    name: str              # "J105443" or k-space name or user alias
    jclass: str | None     # "C2" — from catalog
    statics: str | None    # "3,H"
    effect: str | None     # "Magnetar"
    sigs: list[Signature]
    connections: list[Connection]

@dataclass
class Chain:
    name: str              # named chains, "home" default
    root: System
    location: list[str]    # path of sig prefixes from root = current system
```

Timestamps on everything — that's what unlocks EOL/lifetime display, which bashmapper
structurally cannot do.

### Persistence + undo

JSON snapshot per mutation into `~/.local/state/vagari/<chain>/` (platformdirs
equivalent paths on macOS/Windows), ring-buffered to ~100 snapshots. Undo/redo = pointer
into the ring. Autoload last chain on start. This replaces bashmapper's three `cp -r`
backups with unbounded-enough history for free.

### Reconciliation (`add` / `lazy`)

Per pasted line, match on sig prefix:
- New prefix → create sig, report in "NEW SIGNATURES".
- Existing → merge: keep the **more informative** record (higher signal wins; a real
  Name beats empty; user label always survives). Replaces bashmapper's
  string-length heuristic with explicit rules — same behavior, no accidents.
- `lazy` additionally: sigs in the current system missing from the paste → report in
  "DESPAWNED", one key to confirm-delete all. Never auto-delete a sig that has an open
  connection with mapped children under it — warn instead.

### Command grammar (bashmapper-compatible where sensible)

Command bar (`:` or just typing, fzf-ish):
`add` (or paste directly — paste anywhere ingests), `lazy`, `undo`/`redo`,
`nav abc [def ...]`, `up`, `top`, `abc <label...>`, `abc <jcode>` (auto-enrich from
catalog + create child system), `abc <whtype>` (e.g. `abc H296` sets type + destination
class), `flag abc ...`, `del abc ...`, `eol abc`, `crit abc`, `chain <name>`.

Direct keys on the tree: arrows/hjkl navigate, `Enter` = nav into, `u` = up, `g` = top,
`1/2/3` = full/paths/gas views, `e` = toggle EOL, `x` = flag, `dd` = delete, `?` = help.

### UI layout

btop-style like HARUSPEX: main panel = chain `Tree` (Textual built-in; node labels carry
glyphs: `~` wormhole, `—Relic—`/`—Data—` etc., `!` flag, EOL shown as dimmed/red with
age), right panel = detail for cursor node (system: class/statics/effect/sig table with
signal %; wormhole: type, age, mass, lifetime estimate), bottom = command bar + status
strip (current location breadcrumb, NEW/DESPAWNED reports after a paste). Location
marker (`◉ YOU`) on the current system.

Voice: CARTOGRAPHY DIVISION. Empty states get the ALL-CAPS treatment ("HARUSPEX MAKES NO
REPRESENTATIONS REGARDING THE PERSISTENCE OF SPACETIME. DEPOSIT SCAN TELEMETRY TO
PROCEED."). Same palette, extracted to `theme.tcss`.

## Milestones

**M1 — engine, no UI.** ✅ DONE (2026-08-06). Model + store + scanner parser +
reconcile + catalog loader; 34 fixture-driven tests green; round-trip demo
(`scripts/demo_roundtrip.py`) passing.

**M2 — TUI parity-plus.** ✅ DONE (2026-08-06). App shell, chain tree, detail panel,
command bar (bashmapper grammar + `sweep`), paste-anywhere ingestion with lazy arming,
full/paths/gas views, unbounded undo/redo, named chains, help overlay, Ministry voice
(Anoikis Cartographic Bureau). 54 tests incl. headless pilot smoke tests; SVG
screenshots via `scripts/screenshot.py`. Local tag v0.1.0.

**M3 — enrichment + timers.** ✅ DONE (2026-08-06). Lifetime countdowns from
`wormhole_types.json` (HEALTHY/WANING/EXPIRED/EOL, tree badges + detail panel; upper
bound from first mapping, in-game EOL caps at 4h); region/shattered from catalog in
detail; ESI system-kills enrichment (one public bulk request, fail-silent offline,
`recon` command + fetch on launch) showing per-system hostile/NPC activity. 65 tests;
live ESI path verified. Deferred to M4+: per-pilot/inhabitant enrichment via zKill —
lift patterns from haruspex `enrichers/` and mogglemoss/retrospex when we get there.
Exit: v0.2 (tagged locally).

**M4 — the map follows you.** ✅ DONE (2026-08-06). Chatlog tailer (UTF-16LE, rotation-
aware, replays only the LAST system change from history so stale jumps don't march the
marker); on system change: move into a mapped child, back to the parent, or anywhere in
the chain (BFS); unmapped arrivals become a pending K162 filed with `k`/`k162` (Z-series
placeholder sig, catalog-enriched destination). Fresh chains auto-name their root from
the first arrival; `here <name>` names any system manually. VAGARI_LOG_DIR overrides
detection (macOS/Windows Documents, Steam Proton, Flatpak). 79 tests incl. an
end-to-end pilot test with a real tmp chatlog. Exit: v0.3 (tagged locally).

**M5 — release.** ✅ DONE (2026-08-06). `vagari.spec` (--onedir; universal2 only under
VAGARI_UNIVERSAL2=1 in CI since local Pythons are single-arch; thin launcher entry so
Textual's CSS_PATH resolves inside the frozen package — direct-script entry broke it;
theme.tcss bundled at both paths as insurance), `--version` flag doubling as a bundled-
data self-test, three-platform GitHub Actions matrix (pytest + build + frozen-binary
smoke per platform, release on v* tags). Verified locally: frozen binary draws the full
TUI in a pty and quits clean. Tag v0.4.0 (local; CI runs on first push to a remote).

**M6 — site intelligence + polish.** ✅ DONE (2026-08-06). Site classifier ported from
PANTOSCOPE's probeScan.ts (canonical in retrospex; AUGUR desktop vendors it): ghost
sites TIMED, sleeper caches CACHE, Observatory/AEGIS traps, sleeper relic/data class
bands, unguarded pirate tiers with worth lines, gas reservoir contents to the unit —
no price checks by design. Rendered in the sig detail panel. Plus: animated mascot
header (HARUSPEX genus), about screen (`a`), Ministry-issue command palette, and
random Bureau farewells on quit. 89 tests.

**M7 — polish + operability.** ✅ DONE (2026-08-06). Kind column in the tree (WORMHOLE/
RELIC/DATA/GHOST/GAS/COMBAT/UNFILED — ghost sites detected by name); plain-text chain
export (`c`/`copy`, bashmapper's shareability restored); K162 placeholder re-key
(`zaa = abc`, preserves mapped subtree); location-only commits amend instead of append
(roaming no longer burns undo history); stale sigs dim after 6h unconfirmed, fresh ones
carry a ● for 15 min; `cull` strikes holes past book lifetime (guarded, `cull!`
forces); lifetime/mass gauges in the detail panel; weather-effect attribute tables by
class (effects.json + classes.json — C13 hits like C6); auto-recon every 10 min with a
per-system PvP-trend sparkline; esca flares on events; about screen (Ministry links:
observance.app/ministry roster, PANTOSCOPE, PERISCOPE). 104 tests.

**M8 — find, exits, intel.** ✅ DONE (2026-08-06). `/query` search across system names,
sig prefixes, site names, and labels with match cycling; k-space exits auto-resolve
security + region via public ESI once named (rounded-sec banding — 0.45 rounds to
highsec; session cache, fail-silent); `intel` files a zKillboard dossier for the
current system (all-time ships destroyed, active hunters, recent kills — manual, so
politely rate-limited by design); OneDrive Documents added to Windows chatlog
detection. Both endpoints live-verified before implementation. 116 tests.

## Risks / open items

- **Probe-scanner clipboard format drift / localization**: parse defensively, keep
  fixtures from a real client; non-English clients out of scope for v1 (bashmapper has
  the same constraint, undocumented).
- ~~Catalog staleness / wormhole type DB~~ Resolved: spookyspace's anoik.is-derived data
  covers C13/shattered/drifter/Thera systems and all 90 wormhole types with mass and
  lifetime; refresh by re-running spookyspace's ingest.
- **Dev-env gotcha**: iCloud marks `.venv` contents hidden under `~/Documents`, and
  Python 3.11+ skips hidden `.pth` files → editable imports break outside the project
  root. Repo scripts and `tests/conftest.py` insert the project root into `sys.path`
  themselves; keep doing that for new entry points.
- **Textual Tree ergonomics** at 30+ system chains — validate early in M2; fall back to a
  custom renderable if `Tree` fights the glyph-dense labels.
- Final name/brand: TBD before M5 (repo, binary, config dir all currently `vagari`).

## Backlog

- **`home <name|off>` — designate any system as home.** Today `home` retraces to the
  fragment root; there is no user-set home. Design (scoped 2026-08-12): an `is_home`
  marker on `System` (travels through rekey/sever/adoption like `adrift_since`; one
  additive dict field, legacy snapshots load untouched); `home <name>` resolves via
  `_find_system`, `home off` clears, bare `home` routes as today with the root as
  fallback; `homeward()` grows an up-to-common-ancestor-then-down walk (up legs name
  doors by `return_prefix`, down legs by near-side `sig_prefix`); `⌂` glyph in the
  tree. Edge cases: home in another fragment → "home is adrift"; home struck → flag
  dies with the node, fall back to root. Undo/redo free (flag lives in the snapshot).
  ~100–140 lines + half a dozen session tests.
