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

        # Type position: `abc H2…` — complete wormhole type codes.
        if len(parts) == 2 and len(last) >= 1:
            upper = last.upper()
            for code in sorted(load_wormhole_types()):
                if code.startswith(upper) and code != upper:
                    return value + code[len(last):]
        return None
