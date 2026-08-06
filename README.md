# VAGARI

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/mogglemoss/vagari)](https://github.com/mogglemoss/vagari/releases)
[![Build Status](https://github.com/mogglemoss/vagari/actions/workflows/build.yml/badge.svg)](https://github.com/mogglemoss/vagari/actions/workflows/build.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-C15F3C)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-3a3530)](LICENSE)

<img src="assets/cormorantfell-portrait.jpeg" width="72" align="right">

> [Cormorant Fell](https://evewho.com/character/93594488) — WiNGSPAN alumni, wormhole resident, and a man whose home address is best described as "recently" — built this. It maps where you have been. It follows where you go. It does not ask why.

**Anoikis Cartographic Bureau · Chain Custody Instrument · Capsuleer Edition**

VAGARI — Latin, *to wander* — is a terminal-based wormhole chain mapper for EVE Online. A TUI: it lives in your terminal, runs on keyboard input, and renders entirely in text. You paste your probe scanner into it. It maintains a chain of custody from your home hole to wherever you have unwisely gone, and — if you let it read your chat logs — it moves your marker as you jump, like a colleague quietly updating the incident report while you make the incident.

Single pilot. Local state. No login, no server, no ESI authentication, no browser tab with fourteen other people's route planning in it. The region is named Anoikis — *homelessness* — and the Bureau considers it fitting that its residents should at least know which way they came in.

```
FORM ACB-01 (CHAIN CUSTODY)

THE ANOIKIS CARTOGRAPHIC BUREAU MAKES NO REPRESENTATIONS REGARDING
THE PERSISTENCE OF SPACETIME.

EVERYTHING BELOW OBSERVES; NOTHING BELOW JUDGES.
THE BUREAU IS MERELY NOTING.
```

---

![VAGARI — chain tree with lifetime countdowns, detail panel, and the Bureau's paperwork](assets/vagari.png)

---

## What It Does

**The chain is a tree.** Systems branch through wormholes; every signature is addressed by its three-letter prefix; your position is marked `◉ YOU`. Views filter the record to what matters right now: everything (`1`), wormholes only (`2`), wormholes and gas (`3`). This interaction model is inherited, with respect, from [bashmapper](https://github.com/chloroken/bashmapper) — see Provenance below.

**Deposits are the only ingestion.** Ctrl+A, Ctrl+C in your probe scanner, paste anywhere in the instrument. New signatures are filed, existing ones are enriched — signal strength only rises, names only improve, your labels always survive. The paste is the source of truth and the Bureau reconciles against it; it does not argue with it.

`lazy` arms strict reconciliation: the next deposit also reports which signatures have despawned, and `sweep` strikes them from the record. A wormhole with mapped systems behind it is never struck by a sweep. The Bureau does not shred files that other files refer to.

**The map follows you.** VAGARI tails your EVE chat logs (locally; CCP writes them precisely so tools may read them) and moves `◉ YOU` as you jump — down through mapped holes, back up, or to wherever in the chain you have turned out to be. Arrive somewhere unmapped and the Bureau notes the discrepancy and offers you a form: press `k` and the arrival is filed as a K162 with a placeholder signature, destination class, statics, and weather already annotated. Relabel it when you scan the real sig. On a fresh chain, the first system you visit names your root — setup is "start the instrument, undock."

**Wormholes carry countdowns.** Type a hole (`abc H296`) and it knows its target class, mass, size, and book lifetime. The tree shows an upper-bound countdown — `≤13h04m` — amber when waning, and `EXPIRED?` when the paperwork has outlived the physics. Mark end-of-life in one key; the estimate caps itself at four hours accordingly. The bound is honest: it counts from when *you* first mapped the hole, which is the only fact the Bureau actually possesses.

**Reconnaissance, on request.** `recon` files one unauthenticated request to ESI's public kill feed and annotates every system in your chain with last-hour ship, pod, and NPC kills. Offline it declines to guess. THE BUREAU DOES NOT SPECULATE OFFLINE.

**Everything is undoable.** Every mutation is a snapshot; `z` and `Z` walk the record backward and forward without limit of consequence. Multiple chains of custody are maintained with `chain <name>`. The Bureau has never lost a chain. The Bureau has, on occasion, misplaced a pilot.

---

## Installation

Prebuilt binaries for macOS (universal), Linux, and Windows are on the
[releases page](https://github.com/mogglemoss/vagari/releases). Unpack, run `vagari`.

Or install with [uv](https://docs.astral.sh/uv/):

```
uv tool install git+https://github.com/mogglemoss/vagari
```

Or from source:

```
git clone https://github.com/mogglemoss/vagari
cd vagari
uv sync
uv run vagari
```

---

## Configuration

None required. VAGARI auto-detects your EVE chat log directory on macOS, Windows, Linux (Steam/Proton), and Linux (Steam Flatpak). If yours is elsewhere, say so:

```
VAGARI_LOG_DIR=/path/to/EVE/logs/Chatlogs vagari
```

If no logs are found, follow-me simply stays off and the instrument works as a manual mapper. State lives in your platform's application-state directory, one folder per chain, as plain JSON you may read, back up, or ignore.

---

## The Grammar

| Submission | Effect |
|------------|--------|
| *paste* | deposit scan telemetry (implicit add) |
| `lazy` | arm strict reconciliation for the next deposit |
| `sweep` | strike despawned signatures from the record |
| `nav abc` | proceed through wormhole ABC |
| `up` / `top` | return toward / to the root |
| `abc J105443` | open ABC to a catalogued system (class, statics, weather) |
| `abc H296` | type wormhole ABC (target class, lifetime, mass) |
| `abc <words>` | label a signature |
| `here <name>` | name the current system |
| `flag abc` / `del abc` | flag · strike (`del!` forces) |
| `eol abc` / `crit abc` | toggle end-of-life · cycle mass state |
| `k162` | file a pending unmapped arrival |
| `chain <name>` | switch chain of custody |
| `recon` | refresh system activity from ESI |
| `undo` / `redo` | the record, backward and forward |

| Key | Action |
|-----|--------|
| `Enter` | proceed into the selected wormhole |
| `u` / `g` | up · top |
| `1` `2` `3` | full · paths · gas views |
| `e` `m` `x` `d` | EOL · mass · flag · strike (selected sig) |
| `k` | file unmapped arrival as K162 |
| `l` | arm lazy |
| `z` / `Z` | undo · redo |
| `:` | focus the submission line |
| `?` | reference · `q` quit |

---

## Technical Specifications

| Component | Detail |
|-----------|--------|
| Chain model | Tree of systems · timestamped signatures · JSON snapshots |
| Undo | Unbounded · one snapshot per mutation · ring of 100 |
| Scanner parsing | Tab-delimited probe scanner paste · keeps signal % |
| Reconciliation | Monotonic merge · labels survive · guarded sweeps |
| J-space catalogue | 2,604 systems · class · statics · weather · shattered |
| Wormhole types | 90 types · target class · mass · lifetime · size |
| Lifetime model | Upper bound from first mapping · EOL caps at 4h |
| Follow-me | UTF-16LE chatlog tail · 1 s poll · rotation-aware |
| Activity | ESI system kills · one bulk request · fail-silent |
| Network required | Mapping: no · recon: yes |
| Auth required | None · public endpoints only |

---

## Data Sources

| Source | Purpose | Auth |
|--------|---------|------|
| Bundled J-space catalogue | System class, statics, weather, wormhole types | None |
| ESI `/universe/system_kills/` | Last-hour activity per system | None |
| `~/Documents/EVE/logs/` | Live chatlog tailing (follow-me) | Local read |

---

## Platform Support

| Platform | Binaries | Log Auto-Detection |
|----------|----------|--------------------|
| macOS | Universal (arm64 + x86_64) | Yes |
| Windows | Yes | Yes (default Documents path) |
| Linux (Steam/Proton) | Yes | Yes |
| Linux (Steam Flatpak) | Yes | Yes |

---

## A Note on Cartography

VAGARI records where you have been. This is not the same as knowing where you are safe, which is nowhere, or where the chain ends, which is wherever you stop scanning. A wormhole's lifetime countdown is an upper bound computed from the moment you filed it — the hole was older than that when you found it, and holes, like all Bureau clients, decline to state their age.

A mapped chain is most useful when combined with a scanning habit, a healthy fear of K162s, and the understanding that the map being tidy has never once prevented the territory from eating someone.

Wander accordingly.

---

## Provenance

- **Interaction model** — inspired by [bashmapper](https://github.com/chloroken/bashmapper) by **chloroken** (MIT), a ~250-line bash script whose central insight — the chain is a tree, the paste is the truth, three letters address everything — survives here intact. No code is shared; the philosophy is.
- **J-space reference data** — derived from [anoik.is](https://anoik.is)'s static bundle (which itself builds on CCP's Static Data Export), via the Anoikis Cartographic Bureau's own ingest. See [vagari/data/ATTRIBUTION.md](vagari/data/ATTRIBUTION.md).
- **Sibling instruments** — [HARUSPEX](https://github.com/mogglemoss/haruspex) (proximity intelligence), from which VAGARI inherits its palette, its packaging, and its institutional temperament.

---

## License

MIT — see [LICENSE](LICENSE)

---

*Built with [Textual](https://textual.textualize.io). Uses the [EVE Online ESI API](https://esi.evetech.net). Not affiliated with or endorsed by CCP Games. EVE Online and all related marks are the intellectual property of CCP hf.*

---

— [Cormorant Fell](https://evewho.com/character/93594488), whereabouts filed under pending
