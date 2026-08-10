"""Right-hand detail panel for the selected tree node."""

from __future__ import annotations

from textual.widgets import Static

from vagari.model.chain import System
from vagari.model.lifetime import LifeStatus, assess, hours_text
from vagari.parsers.catalog import lookup_system, lookup_wh_type
from vagari.parsers.site_intel import classify_site, gas_contents
from vagari.session import Session
from vagari.ui.chain_tree import DIM, MUTED, RUST, TEXT, WARN, age_text
from vagari.ui.graphs import gauge, spark

def human_mass(kg: float) -> str:
    """3_000_000_000 → '3.0B kg' — the units wormholers actually say."""
    if kg >= 1e9:
        return f"{kg / 1e9:.1f}B kg"
    if kg >= 1e6:
        return f"{kg / 1e6:.1f}M kg"
    return f"{kg:,.0f} kg"


EMPTY_STATE = f"""\
[{MUTED}]FORM ACB-01 (CHAIN CUSTODY)[/{MUTED}]

[{MUTED}]DEPOSIT SCAN TELEMETRY BY PASTING IT
ANYWHERE IN THIS INSTRUMENT.

THE ANOIKIS CARTOGRAPHIC BUREAU MAKES NO
REPRESENTATIONS REGARDING THE PERSISTENCE
OF SPACETIME.

EVERYTHING BELOW OBSERVES; NOTHING BELOW
JUDGES. THE BUREAU IS MERELY NOTING.[/{MUTED}]"""


class DetailPanel(Static):
    def __init__(self, session: Session, **kwargs) -> None:
        super().__init__(EMPTY_STATE, **kwargs)
        self.session = session

    def show_node(self, data: tuple | None) -> None:
        if data is None:
            self.update(EMPTY_STATE)
            return
        if data[0] == "system":
            self._show_system(self.session.chain.system_at(data[1]), data[1])
        else:
            self._show_sig(data[1], data[2])

    def _show_system(self, system: System, path: list | None = None) -> None:
        lines = [f"[bold {RUST}]{system.name}[/bold {RUST}]"]
        if path is not None and len(path) == 1 and len(self.session.chain.roots) > 1:
            n = path[0] + 1
            lines.append(
                f"[{MUTED}]fragment #{n} · "
                f"[@click=app.sig_cmd('del')]discard[/][/{MUTED}]"
            )
        if system.jclass:
            statics = f" · statics {system.statics}" if system.statics else ""
            lines.append(f"[{TEXT}]{system.jclass}{statics}[/{TEXT}]")
        if system.effect:
            lines.append(f"[{WARN}]{system.effect}[/{WARN}]")
        kinfo = self.session.kspace.get(system.name)
        if kinfo is not None:
            sec_color = {"H": TEXT, "L": WARN, "N": DIM}[kinfo.band]
            lines.append(
                f"[{sec_color}]security {kinfo.sec_display}[/{sec_color}] "
                f"[{MUTED}]· region {kinfo.region}[/{MUTED}]"
            )
        zstats = None
        if kinfo is not None:
            zstats = self.session.zkill_stats.get(kinfo.system_id)
        info = lookup_system(system.name)
        if info is not None and zstats is None:
            zstats = self.session.zkill_stats.get(info.system_id)
        if zstats is not None:
            lines.append(
                f"[{MUTED}]ZKILL: {zstats.ships_destroyed:,} ships destroyed "
                f"all-time · {zstats.active_characters} active hunters · "
                f"{zstats.active_kills} recent kills[/{MUTED}]"
            )
        if system.effect and info is not None:
            from vagari.parsers.catalog import effect_details

            for attr, value in effect_details(system.effect, info.class_key) or []:
                lines.append(f"  [{MUTED}]{attr}[/{MUTED}] [{TEXT}]{value}[/{TEXT}]")
        if info is not None:
            extras = []
            if info.region:
                extras.append(f"region {info.region}")
            if info.shattered:
                extras.append("SHATTERED")
            if extras:
                lines.append(f"[{MUTED}]{' · '.join(extras)}[/{MUTED}]")
            activity = self.session.activity.get(info.system_id)
            if activity is not None:
                color = WARN if activity.hostile else MUTED
                lines.append(
                    f"[{color}]ACTIVITY (last hour): {activity.ship_kills} ship · "
                    f"{activity.pod_kills} pod · {activity.npc_kills} NPC[/{color}]"
                )
            elif self.session.activity_fetched:
                lines.append(f"[{MUTED}]ACTIVITY (last hour): none observed[/{MUTED}]")
            history = self.session.activity_history.get(info.system_id, [])
            if len(history) >= 2:
                trend_color = WARN if history[-1] > 0 else MUTED
                lines.append(
                    f"[{MUTED}]TREND (PvP, per recon):[/{MUTED}] "
                    f"[{trend_color}]{spark(history)}[/{trend_color}]"
                )
        lines.append("")
        if system.sigs:
            lines.append(f"[{MUTED}]SIGNATURES ({len(system.sigs)})[/{MUTED}]")
            spec = "/".join(str(p) for p in (path or [0]))
            for sig in system.sigs:
                name = sig.label or sig.name or "—"
                pct = f"{sig.signal:>3.0f}%"
                flag = "!" if sig.flagged else " "
                lines.append(
                    f"[{TEXT}][@click=app.select_at('{spec}', '{sig.prefix}')]"
                    f"{sig.prefix}[/][/{TEXT}]{flag}"
                    f"[{MUTED}]{pct} {sig.group.value:<12} {name}[/{MUTED}]"
                )
        else:
            lines.append(f"[{MUTED}]NO SIGNATURES ON RECORD.[/{MUTED}]")
        self.update("\n".join(lines))

    def _show_sig(self, path: list, prefix: str) -> None:
        system = self.session.chain.system_at(path)
        sig = system.find_sig(prefix)
        if sig is None:
            self.update(EMPTY_STATE)
            return
        conn = system.find_connection(prefix)

        def link(label: str, action: str, color: str = MUTED) -> str:
            return f"[{color}][@click=app.{action}]{label}[/][/{color}]"

        actions = []
        if conn is not None:
            actions.append(link("nav", "nav_selected", RUST))
        actions += [
            link("eol", "sig_cmd('eol')"),
            link("mass", "sig_cmd('crit')"),
            link("flag", "sig_cmd('flag')"),
            link("strike", "sig_cmd('del')"),
        ]
        if conn is None:
            actions.append(link("return", "return_selected"))
        action_row = f"[{DIM}]·[/{DIM}]".join(f" {a} " for a in actions)
        lines = [
            f"[bold {RUST}]{sig.prefix}[/bold {RUST}] [{MUTED}]in {system.name}[/{MUTED}]",
            action_row,
            f"[{TEXT}]{sig.group.value}[/{TEXT}] [{MUTED}]· signal {sig.signal:.1f}%[/{MUTED}]",
        ]
        # The far side of the hole we came through: one wormhole, two sigs.
        if len(path) > 1:
            parent = self.session.chain.system_at(path[:-1])
            via = parent.find_connection(path[-1])
            if via is not None and via.return_prefix == sig.prefix:
                pair = f"{via.wh_type} " if via.wh_type else ""
                lines.append(
                    f"[bold {RUST}]RETURN[/bold {RUST}] [{MUTED}]— the far side "
                    f"of {pair}{via.sig_prefix} in {parent.name}. One hole, "
                    f"two signatures; its clock and mass are shared.[/{MUTED}]"
                )
        if sig.name:
            lines.append(f"[{TEXT}]{sig.name}[/{TEXT}]")
        if sig.label:
            lines.append(f"[{WARN}]“{sig.label}”[/{WARN}]")
        if sig.flagged:
            lines.append(f"[bold {WARN}]FLAGGED FOR ATTENTION[/bold {WARN}]")
        lines.append(
            f"[{MUTED}]first noted {age_text(sig.first_seen)} ago · "
            f"last confirmed {age_text(sig.last_seen)} ago[/{MUTED}]"
        )
        verdict = classify_site(sig.group, sig.name)
        if verdict is not None:
            lines.append("")
            badge_color = RUST if verdict.hazard else TEXT
            lines.append(
                f"[bold {badge_color}]{verdict.label}[/bold {badge_color}] "
                f"[{MUTED}]{verdict.note}[/{MUTED}]"
            )
            if verdict.worth:
                lines.append(f"[{MUTED}]Worth: {verdict.worth}[/{MUTED}]")
            clouds = gas_contents(sig.name)
            if clouds:
                contents = " · ".join(f"{c.units:,} × {c.gas}" for c in clouds)
                lines.append(f"[{TEXT}]{contents}[/{TEXT}]")
        from vagari.model.chain import SigGroup
        from vagari.parsers.catalog import candidate_types

        if sig.group is SigGroup.WORMHOLE and (conn is None or not conn.wh_type):
            candidates = candidate_types(system.name)
            if candidates:
                info = lookup_system(system.name)
                static_codes = set(info.statics) if info else set()
                lines.append("")
                lines.append(
                    f"[{MUTED}]CANDIDATE TYPES for a hole in "
                    f"{system.name}:[/{MUTED}]"
                )
                for t in candidates[:9]:
                    marker = " static" if t.code in static_codes else ""
                    life = f" · {t.lifetime_hours:g}h" if t.lifetime_hours else ""
                    color = TEXT if marker else MUTED
                    lines.append(
                        f"  [{color}][@click=app.set_selected_type('{t.code}')]"
                        f"{t.code} → {t.target_display}{life}{marker}[/][/{color}]"
                    )
                lines.append(
                    f"  [{DIM}](click a candidate to type this hole)[/{DIM}]"
                )
                if len(candidates) > 9:
                    lines.append(f"  [{MUTED}]… and {len(candidates) - 9} more[/{MUTED}]")
        if conn is not None:
            lines.append("")
            lines.append(f"[{MUTED}]WORMHOLE — leads to[/{MUTED}] "
                         f"[{TEXT}]{conn.child.name}[/{TEXT}]")
            wh_type = lookup_wh_type(conn.wh_type) if conn.wh_type else None
            if wh_type is not None:
                # K162s carry no book data — target, mass, and lifetime are
                # all None; format only what the type actually declares.
                bits = [f"{wh_type.code} → {wh_type.target_display}"]
                if wh_type.size and wh_type.size != "unknown":
                    bits.append(wh_type.size)
                if wh_type.lifetime_hours:
                    bits.append(f"lifetime {wh_type.lifetime_hours:g}h")
                bits.append(f"open {age_text(conn.opened_at)}")
                lines.append(f"[{MUTED}]{' · '.join(bits)}[/{MUTED}]")
                mass_bits = []
                if wh_type.total_mass:
                    mass_bits.append(f"total {human_mass(wh_type.total_mass)}")
                if wh_type.jump_mass:
                    mass_bits.append(f"per jump ≤{human_mass(wh_type.jump_mass)}")
                if wh_type.mass_regen:
                    mass_bits.append(f"regen {human_mass(wh_type.mass_regen)}/day")
                if mass_bits:
                    lines.append(f"[{MUTED}]{' · '.join(mass_bits)}[/{MUTED}]")
                life = assess(conn)
                if life.remaining_hours is not None:
                    if life.status is LifeStatus.EXPIRED:
                        lines.append(
                            f"[bold {DIM}]PAST BOOK LIFETIME — verify and cull[/bold {DIM}]"
                        )
                    else:
                        color = WARN if life.status in (
                            LifeStatus.WANING, LifeStatus.EOL
                        ) else MUTED
                        fraction = (
                            life.remaining_hours / life.total_hours
                            if life.total_hours else 0
                        )
                        lines.append(
                            f"[{color}]LIFE {gauge(fraction)} "
                            f"≤{hours_text(life.remaining_hours)} remaining "
                            f"(upper bound)[/{color}]"
                        )
            else:
                lines.append(f"[{MUTED}]open {age_text(conn.opened_at)}[/{MUTED}]")
            mass_fraction = {"fresh": 1.0, "reduced": 0.5, "critical": 0.1}[conn.mass.value]
            mass_color = MUTED if conn.mass.value == "fresh" else WARN
            lines.append(
                f"[{mass_color}]MASS {gauge(mass_fraction, cells=3)} "
                f"{conn.mass.value.upper()}[/{mass_color}]"
            )
            if conn.eol:
                lines.append(f"[bold {DIM}]END OF LIFE[/bold {DIM}]")
        self.update("\n".join(lines))
