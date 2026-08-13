"""Ghost-text completion for the submission line.

Fish-style: the suggestion renders dim ahead of the cursor; → accepts it.
Completes command words, wormhole type codes in the type position, and
pilot names after `pilot`.
"""

from __future__ import annotations

from textual.suggester import Suggester

from vagari.commands import first_words
from vagari.parsers.catalog import load_wormhole_types

_COMMANDS = first_words() + ["redo", "full", "paths", "sites", "gas", "combat"]


class BureauSuggester(Suggester):
    def __init__(self, session) -> None:
        super().__init__(use_cache=False, case_sensitive=False)
        self.session = session

    async def get_suggestion(self, value: str) -> str | None:
        if not value or value.endswith(" "):
            return None
        parts = value.split()
        head, last = parts[0].lower(), parts[-1]

        if len(parts) == 1:
            for word in _COMMANDS:
                if word.startswith(last.lower()) and word != last.lower():
                    return value + word[len(last):]
            return None

        if head == "pilot":
            typed = " ".join(parts[1:]).lower()
            for name in sorted(self.session.known_pilots):
                if name.lower().startswith(typed) and name.lower() != typed:
                    return value + name[len(typed):]
            return None

        if head == "here" and len(parts) == 2:
            return self._complete_system(value, last, min_len=1)

        # Type position: `abc H2…` — wormhole type codes first, then
        # system names (chain first, then the whole k-space chart).
        if len(parts) == 2 and len(last) >= 1:
            upper = last.upper()
            for code in sorted(load_wormhole_types()):
                if code.startswith(upper) and code != upper:
                    return value + code[len(last):]
            return self._complete_system(value, last, min_len=2)
        return None

    def _chain_names(self) -> list[str]:
        names: list[str] = []

        def walk(system) -> None:
            if system.name and not system.name.startswith("?"):
                names.append(system.name)
            for conn in system.connections:
                walk(conn.child)

        for root in self.session.chain.roots:
            walk(root)
        return names

    def _complete_system(self, value: str, last: str, min_len: int) -> str | None:
        if len(last) < min_len:
            return None
        from vagari.parsers.catalog import kspace_names

        typed = last.lower()
        for name in self._chain_names() + kspace_names():
            if name.lower().startswith(typed) and name.lower() != typed:
                return value + name[len(last):]
        return None
