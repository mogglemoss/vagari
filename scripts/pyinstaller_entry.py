"""PyInstaller entry point.

A thin launcher so MapperApp's defining module is vagari.main (not a
top-level script) — Textual resolves CSS_PATH relative to the defining
module's file, which must map to _internal/vagari/ui/ in the frozen app.
"""

from vagari.main import main

if __name__ == "__main__":
    main()
