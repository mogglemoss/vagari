"""Chain search inside the command palette: Ctrl+P, type a system, sig,
or label — jump the cursor there. The palette stops being a menu and
becomes navigation."""

from __future__ import annotations

from functools import partial

from textual.command import Hit, Hits, Provider


class ChainSearchProvider(Provider):
    @property
    def _app(self):
        return self.screen.app

    def _entries(self):
        session = self._app.session
        for data in session.find_matches(""):
            yield data
        # find_matches("") is empty by design; walk everything instead.
        chain = session.chain

        def walk(path, system):
            label = system.name
            yield (f"{label}", ("system", path))
            for sig in system.sigs:
                text = f"{sig.prefix} {sig.label or sig.name}".strip()
                yield (f"{text} · in {label}", ("sig", path, sig.prefix))
            for conn in system.connections:
                yield from walk(path + [conn.sig_prefix], conn.child)

        for ri, root in enumerate(chain.roots):
            yield from walk([ri], root)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        app = self._app
        for text, data in self._entries():
            score = matcher.match(text)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(text),
                    partial(app.jump_to_data, data),
                    help="in the chain",
                )
