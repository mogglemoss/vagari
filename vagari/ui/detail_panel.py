"""Right-hand detail panel for the selected tree node."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Digits, Input, Sparkline, Static

from vagari.model.chain import SigGroup, System, utcnow
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


def _link(label: str, action: str, color: str = MUTED) -> str:
    return f"[{color}][@click=app.{action}]{label}[/][/{color}]"


def _rule(title: str) -> str:
    """A section rule: ── TITLE ─────────"""
    bar = "─" * max(3, 26 - len(title))
    return (
        f"[{DIM}]──[/{DIM}] [bold {MUTED}]{title}[/bold {MUTED}] "
        f"[{DIM}]{bar}[/{DIM}]"
    )


EMPTY_STATE = f"""\
[{MUTED}]FORM ACB-01 (CHAIN CUSTODY)[/{MUTED}]

[{MUTED}]DEPOSIT SCAN TELEMETRY BY PASTING IT
ANYWHERE IN THIS INSTRUMENT.

THE ANOIKIS CARTOGRAPHIC BUREAU MAKES NO
REPRESENTATIONS REGARDING THE PERSISTENCE
OF SPACETIME.

EVERYTHING HERE OBSERVES; NOTHING HERE
JUDGES. THE BUREAU IS MERELY NOTING.[/{MUTED}]"""


class DetailPanel(VerticalScroll):
    """The dossier: a markup body plus real widgets — a sortable signature
    table, a native sparkline for the activity trend, and a Digits readout
    for an EOL countdown."""

    def __init__(self, session: Session, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session = session
        self.table_path: list = [0]
        self._form_wrap: tuple[str, str] | None = None
        self._showing: tuple | None = None

    def compose(self) -> ComposeResult:
        # The filing field sits between the head (identity, actions) and
        # the body (sections): it belongs to the entity, not to whatever
        # section happens to end the body.
        yield Static("", id="dossier-head")
        yield Input(id="dossier-form")
        yield Static(EMPTY_STATE, id="dossier-body")
        yield Digits("", id="dossier-eol")
        yield Sparkline([], id="dossier-trend")
        yield Static("", id="dossier-sigs-header")
        yield DataTable(id="dossier-sigs")

    def on_mount(self) -> None:
        table = self.query_one("#dossier-sigs", DataTable)
        table.add_columns("SIG", "%", "KIND", "NAME")
        table.cursor_type = "row"
        self._extras(False, False, False)

    @property
    def content(self):
        """Head + body markup — for callers (and tests) that read text."""
        head = self.query_one("#dossier-head", Static).content
        body = self.query_one("#dossier-body", Static).content
        return f"{head}\n{body}" if head else str(body)

    def update(self, markup: str, head: str = "") -> None:
        self.query_one("#dossier-head", Static).update(head)
        self.query_one("#dossier-head", Static).display = bool(head)
        self.query_one("#dossier-body", Static).update(markup)

    def _extras(
        self, eol: bool, trend: bool, table: bool,
        form: bool = False, sigs_header: bool = False,
    ) -> None:
        self.query_one("#dossier-eol").display = eol
        self.query_one("#dossier-trend").display = trend
        self.query_one("#dossier-sigs").display = table
        self.query_one("#dossier-form").display = form
        self.query_one("#dossier-sigs-header").display = sigs_header
        if not form:
            self._form_wrap = None

    def _arm_form(self, before: str, after: str, placeholder: str) -> None:
        """Point the dossier's submission field at a filing: what the user
        types is wrapped as `{before} {typed}{after}` and run through the
        same front door as the command line."""
        self._form_wrap = (before, after)
        self.query_one("#dossier-form", Input).placeholder = placeholder

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "dossier-form":
            return
        event.stop()
        value = event.value.strip()
        event.input.value = ""
        if not value or self._form_wrap is None:
            return
        before, after = self._form_wrap
        self.app.submit_text(f"{before} {value}{after}".strip())

    def reshow(self) -> None:
        """Re-render the current subject — for async enrichment landing."""
        self.show_node(self._showing)

    def ensure_subject(self, data: tuple) -> None:
        """Re-render; adopt `data` as the subject first if there is none.
        Enrichment must land somewhere visible, never on a blank form."""
        if self._showing is None:
            self._showing = data
        self.reshow()

    def show_node(self, data: tuple | None) -> None:
        self._showing = data
        if data is None:
            self.update(EMPTY_STATE)
            self._extras(False, False, False)
            return
        try:
            if data[0] == "system":
                self._show_system(
                    self.session.chain.system_at(data[1]), data[1]
                )
            else:
                self._show_sig(data[1], data[2])
        except Exception:
            # The subject vanished from the record (fragment discarded,
            # chain switched) — fall back to ◉ YOU rather than crash.
            fallback = ("system", list(self.session.chain.location))
            if data != fallback:
                self.show_node(fallback)
            else:
                self._showing = None
                self.update(EMPTY_STATE)
                self._extras(False, False, False)

    def _killboard_lines(self, system: System) -> list[str]:
        """The killboard verdict for a system — it always says something.
        Shown on the system's own dossier AND on the wormhole leading to
        it: intel belongs on this side of the hole, before the splash."""
        from vagari.enrichers.zkill import human_isk

        kinfo = self.session.kspace.get(system.name)
        info = lookup_system(system.name)
        system_id = kinfo.system_id if kinfo is not None else (
            info.system_id if info is not None else None
        )
        if system_id is None:
            if system.name and not system.name.startswith("?"):
                hook = getattr(self.app, "maybe_resolve_kspace", None)
                if hook is not None and hook():
                    return [
                        f"  [{MUTED}]identifying {system.name}…[/{MUTED}]"
                    ]
                return [
                    f"  [{MUTED}]{system.name} appears on no chart — name "
                    f"the system and the Bureau will inquire.[/{MUTED}]"
                ]
            return [
                f"  [{MUTED}]system unnamed — nothing to ask after.[/{MUTED}]"
            ]
        zstats = self.session.zkill_stats.get(system_id)
        if zstats is None:
            dispatched = False
            hook = getattr(self.app, "maybe_fetch_intel", None)
            if hook is not None:
                dispatched = hook(system.name, system_id)
            if dispatched:
                return [
                    f"  [{MUTED}]inquiry dispatched — awaiting the void's "
                    f"reply…[/{MUTED}]"
                ]
            return [
                f"  [{MUTED}]nothing on file · "
                f"[@click=app.fetch_intel({system_id}, '{system.name}')]"
                f"inquire[/][/{MUTED}]"
            ]
        lines: list[str] = []
        if zstats.stats is not None:
            s = zstats.stats
            lines.append(
                f"  [{TEXT}]{s.ships_destroyed:,}[/{TEXT}] [{MUTED}]ships · "
                f"[/{MUTED}][{TEXT}]{human_isk(s.isk_destroyed)}[/{TEXT}] "
                f"[{MUTED}]ISK destroyed all-time[/{MUTED}]"
            )
            lines.append(
                f"  [{TEXT}]{s.active_characters}[/{TEXT}] [{MUTED}]hunters "
                f"active · [/{MUTED}][{TEXT}]{s.active_ships}[/{TEXT}] "
                f"[{MUTED}]hulls seen recently[/{MUTED}]"
            )
        lk = zstats.last_kill
        if lk is not None:
            when = f"{age_text(lk.time)} ago" if lk.time else "recently"
            color = WARN if lk.time and (
                (utcnow() - lk.time).total_seconds() < 3600
            ) else MUTED
            lines.append(
                f"  [{color}]LAST KILL: {when} — {lk.ship_name} down, "
                f"{lk.attackers} attacker{'s' if lk.attackers != 1 else ''}"
                f" · {human_isk(lk.isk)} ISK[/{color}]"
            )
            # Structure and NPC kills carry no pilot: lead with whatever
            # identity the killmail does hold.
            by = lk.killer or lk.killer_corp
            org = " · ".join(
                b for b in (lk.killer_corp, lk.killer_alliance)
                if b and b != by
            )
            if by and org:
                by += f" ({org})"
            if by and lk.killer_ship:
                by += f" · {lk.killer_ship}"
            elif not by and lk.killer_ship:
                by = lk.killer_ship
            if by:
                lines.append(
                    f"    [{color}]└ {by.replace('[', chr(92) + '[')}"
                    f"[/{color}]"
                )
        else:
            lines.append(
                f"  [{MUTED}]LAST KILL: none on record — ever.[/{MUTED}]"
            )
        day_old = lk is not None and lk.time is not None and (
            (utcnow() - lk.time).total_seconds() < 86400
        )
        if not day_old:
            lines.append(
                f"  [{DIM}]QUIET — nothing destroyed here in the last "
                f"day. The Bureau declines to be reassured.[/{DIM}]"
            )
        return lines

    def _show_system(self, system: System, path: list | None = None) -> None:
        current = path is not None and list(path) == list(self.session.chain.location)
        title = f"[bold {RUST}]{system.name}[/bold {RUST}]"
        if current:
            title += f"  [{RUST}]◉ YOU ARE HERE[/{RUST}]"
        head = [title]
        is_root = path is not None and len(path) == 1
        if is_root and len(self.session.chain.roots) > 1:
            n = path[0] + 1
            head.append(
                f"[{MUTED}]fragment #{n} · "
                f"[@click=app.sig_cmd('del')]discard[/][/{MUTED}]"
            )
        actions = []
        if not current:
            actions.append(_link("nav", "nav_selected", RUST))
        if current:
            actions.append(_link("recon", "run_cmd('recon')"))
            actions.append(_link("intel", "run_cmd('intel')"))
        if not is_root and system.name and not system.name.startswith("?"):
            actions.append(_link("strike", f"run_cmd('strike {system.name}')"))
        if actions:
            head.append(f"[{DIM}]·[/{DIM}]".join(f" {a} " for a in actions))
        pending = self.session.pending_arrival
        if pending is not None and path is not None and list(path) == list(pending[1]):
            links = [
                _link(c, f"run_cmd('k162 {c}')", TEXT)
                for c in self.session.arrival_candidates()
            ]
            links.append(_link("a fresh hole", "run_cmd('k162!')"))
            head.append(
                f"[bold {WARN}]ARRIVAL UNFILED: {pending[0]}[/bold {WARN}] "
                f"[{MUTED}]— through:[/{MUTED}]"
                + f"[{DIM}]·[/{DIM}]".join(f" {l} " for l in links)
            )
        # Identity: class, statics, region — one tidy block.
        info = lookup_system(system.name)
        if system.jclass:
            statics = system.statics
            if isinstance(statics, (list, tuple)):
                statics = " · ".join(statics)
            statics = f" [{MUTED}]· statics[/{MUTED}] {statics}" if statics else ""
            head.append(f"[{TEXT}]{system.jclass}{statics}[/{TEXT}]")
        if info is not None:
            extras = []
            if info.region:
                extras.append(f"region {info.region}")
            if info.shattered:
                extras.append("SHATTERED")
            if extras:
                head.append(f"[{MUTED}]{' · '.join(extras)}[/{MUTED}]")
        kinfo = self.session.kspace.get(system.name)
        if kinfo is not None:
            sec_color = {"H": TEXT, "L": WARN, "N": DIM}[kinfo.band]
            head.append(
                f"[{sec_color}]security {kinfo.sec_display}[/{sec_color}] "
                f"[{MUTED}]· region {kinfo.region}[/{MUTED}]"
            )
        if system.effect:
            head.append(f"[{WARN}]{system.effect}[/{WARN}]")
            if info is not None:
                from vagari.parsers.catalog import effect_details

                for attr, value in effect_details(
                    system.effect, info.class_key
                ) or []:
                    head.append(
                        f"  [{MUTED}]{attr}[/{MUTED}] [{TEXT}]{value}[/{TEXT}]"
                    )
        lines = [_rule("MATTERS OF DESTRUCTION")]
        lines += self._killboard_lines(system)
        act = []
        history = []
        if info is not None:
            activity = self.session.activity.get(info.system_id)
            if activity is not None:
                color = WARN if activity.hostile else MUTED
                act.append(
                    f"  [{color}]last hour: {activity.ship_kills} ship · "
                    f"{activity.pod_kills} pod · {activity.npc_kills} "
                    f"NPC[/{color}]"
                )
            elif self.session.activity_fetched:
                act.append(f"  [{MUTED}]last hour: none observed[/{MUTED}]")
            history = self.session.activity_history.get(info.system_id, [])
            if len(history) >= 2:
                act.append(f"  [{MUTED}]PvP trend, per recon sweep:[/{MUTED}]")
        if act:
            lines += ["", _rule("DISTURBANCES")] + act
        sigs_header = self.query_one("#dossier-sigs-header", Static)
        if system.sigs:
            sigs_header.update(
                _rule(f"SIGNATURES OF RECORD · {len(system.sigs)}")
            )
        else:
            sigs_header.update(
                _rule("SIGNATURES OF RECORD")
                + f"\n  [{MUTED}]none on record.[/{MUTED}]"
            )
        self.update("\n".join(lines), head="\n".join(head))

        from vagari.glyphs import kind_word

        table = self.query_one("#dossier-sigs", DataTable)
        table.clear()
        self.table_path = list(path or [0])
        for sig in system.sigs:
            name = sig.label or sig.name or "—"
            if len(name) > 22:  # full name is one click away, in the sig view
                name = name[:21] + "…"
            table.add_row(
                sig.prefix + ("!" if sig.flagged else ""),
                f"{sig.signal:.0f}",
                kind_word(sig.group, sig.name),
                name,
                key=sig.prefix,
            )
        if history:
            self.query_one("#dossier-trend", Sparkline).data = history
        if current:
            self._arm_form(
                "here", "", f"here — name or correct {system.name}"
            )
        self._extras(
            False, len(history) >= 2, bool(system.sigs),
            form=current, sigs_header=True,
        )

    def _show_sig(self, path: list, prefix: str) -> None:
        system = self.session.chain.system_at(path)
        sig = system.find_sig(prefix)
        if sig is None:
            # Struck or refiled from under us — fall back to its system.
            self._showing = ("system", list(path))
            self._show_system(system, list(path))
            return
        conn = system.find_connection(prefix)
        life = assess(conn) if conn is not None else None
        show_eol = life is not None and life.remaining_hours is not None
        if show_eol:
            hours = int(life.remaining_hours)
            minutes = int((life.remaining_hours - hours) * 60)
            self.query_one("#dossier-eol", Digits).update(
                f"{hours}:{minutes:02d}"
            )
        qualifier = (
            f" @{system.name}"
            if system.name and not system.name.startswith("?")
            else ""
        )
        if sig.group is SigGroup.WORMHOLE:
            hint = f"{sig.prefix} — type (K162 · H296) · destination (J105443) · label"
        else:
            hint = f"{sig.prefix} — label this signature, filed verbatim"
        self._arm_form(sig.prefix.lower(), qualifier, hint)
        self._extras(show_eol, False, False, form=True)

        link = _link
        actions = []
        if conn is not None:
            actions.append(link("nav", "nav_selected", RUST))
        actions += [
            link("eol", "sig_cmd('eol')"),
            link("mass", "sig_cmd('crit')"),
            link("flag", "sig_cmd('flag')"),
            link("strike", "sig_cmd('del')"),
        ]
        if conn is not None:
            actions.append(link("sever", "sig_cmd('sever')"))
        if conn is None:
            actions.append(link("return", "return_selected"))
        action_row = f"[{DIM}]·[/{DIM}]".join(f" {a} " for a in actions)
        spec = "/".join(str(p) for p in path)
        self._head = [
            f"[bold {RUST}]{sig.prefix}[/bold {RUST}] [{MUTED}]in "
            f"[@click=app.open_system_dossier('{spec}')]{system.name}[/]"
            f"[/{MUTED}]",
            action_row,
            f"[{TEXT}]{sig.group.value}[/{TEXT}] [{MUTED}]· signal {sig.signal:.1f}%[/{MUTED}]",
        ]
        lines = []
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
        from vagari.parsers.catalog import candidate_types

        if sig.group is SigGroup.WORMHOLE and (conn is None or not conn.wh_type):
            candidates = candidate_types(system.name)
            if candidates:
                info = lookup_system(system.name)
                static_codes = set(info.statics) if info else set()
                lines += ["", _rule("PLAUSIBLE DESIGNATIONS")]
                for t in candidates[:10]:
                    if t.code == "K162":
                        lines.append(
                            f"  [{TEXT}][@click=app.set_selected_type('K162')]"
                            f"K162 — inbound; its true type reads from the "
                            f"far side[/][/{TEXT}]"
                        )
                        continue
                    marker = " static" if t.code in static_codes else ""
                    life = f" · {t.lifetime_hours:g}h" if t.lifetime_hours else ""
                    color = TEXT if marker else MUTED
                    lines.append(
                        f"  [{color}][@click=app.set_selected_type('{t.code}')]"
                        f"{t.code} → {t.target_display}{life}{marker}[/][/{color}]"
                    )
                lines.append(
                    f"  [{DIM}]click a candidate — or type any code, even a "
                    f"rare one, in the field below[/{DIM}]"
                )
        if conn is not None:
            lines += ["", _rule("THE PASSAGE")]
            lines.append(f"  [{MUTED}]leads to[/{MUTED}] "
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
                lines.append(f"  [{MUTED}]{' · '.join(bits)}[/{MUTED}]")
                mass_bits = []
                if wh_type.total_mass:
                    mass_bits.append(f"total {human_mass(wh_type.total_mass)}")
                if wh_type.jump_mass:
                    mass_bits.append(f"per jump ≤{human_mass(wh_type.jump_mass)}")
                if wh_type.mass_regen:
                    mass_bits.append(f"regen {human_mass(wh_type.mass_regen)}/day")
                if mass_bits:
                    lines.append(f"  [{MUTED}]{' · '.join(mass_bits)}[/{MUTED}]")
                life = assess(conn)
                if life.remaining_hours is not None:
                    if life.status is LifeStatus.EXPIRED:
                        lines.append(
                            f"  [bold {DIM}]PAST BOOK LIFETIME — verify and "
                            f"cull[/bold {DIM}]"
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
                            f"  [{color}]LIFE {gauge(fraction)} "
                            f"≤{hours_text(life.remaining_hours)} remaining "
                            f"(upper bound)[/{color}]"
                        )
            else:
                lines.append(
                    f"  [{MUTED}]open {age_text(conn.opened_at)}[/{MUTED}]"
                )
            mass_fraction = {"fresh": 1.0, "reduced": 0.5, "critical": 0.1}[conn.mass.value]
            mass_color = MUTED if conn.mass.value == "fresh" else WARN
            lines.append(
                f"  [{mass_color}]MASS {gauge(mass_fraction, cells=3)} "
                f"{conn.mass.value.upper()}[/{mass_color}]"
            )
            if conn.eol:
                lines.append(f"  [bold {DIM}]END OF LIFE[/bold {DIM}]")
            # Far-side intel, on this side of the hole — the whole point is
            # knowing what waits before splashing it.
            far = conn.child.name if conn.child.name else "?"
            lines += ["", _rule(f"WHAT AWAITS · {far}")]
            lines += self._killboard_lines(conn.child)
        while lines and not lines[0]:
            lines.pop(0)
        self.update("\n".join(lines), head="\n".join(self._head))
