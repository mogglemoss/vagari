# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for VAGARI
# Build: uv run pyinstaller vagari.spec
#
# --onedir on purpose: onefile's bootloader re-exec breaks Textual key input
# on Linux (hard-won HARUSPEX lesson). universal2 only in CI (VAGARI_UNIVERSAL2=1);
# local dev Pythons are usually single-arch and can't produce fat binaries.

import os

a = Analysis(
    ["scripts/pyinstaller_entry.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("vagari/data/systems.json", "vagari/data"),
        ("vagari/data/wormhole_types.json", "vagari/data"),
        ("vagari/data/effects.json", "vagari/data"),
        ("vagari/data/classes.json", "vagari/data"),
        ("vagari/data/meta.json", "vagari/data"),
        ("vagari/data/ATTRIBUTION.md", "vagari/data"),
        ("vagari/ui/theme.tcss", "vagari/ui"),
        # Duplicate at the flat path too — cheap insurance against the
        # entry-script-relative CSS resolution.
        ("vagari/ui/theme.tcss", "ui"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="vagari",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="universal2" if os.environ.get("VAGARI_UNIVERSAL2") else None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="vagari",
)
