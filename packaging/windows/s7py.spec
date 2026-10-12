# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spezifikation fuer s7py (Windows .exe, Ordner-Build)."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

SPECDIR = Path(SPECPATH).resolve()
ROOT = SPECDIR.parents[1]  # packaging/windows -> Projektroot

block_cipher = None

snap7_datas, snap7_binaries, snap7_hiddenimports = collect_all("snap7")
mpl_datas, mpl_binaries, mpl_hiddenimports = collect_all("matplotlib")
pil_datas, pil_binaries, pil_hiddenimports = collect_all("PIL")

hiddenimports = [
    "s7py",
    "s7py.__main__",
    "s7py.app",
    "s7py.about",
    "s7py.selftest",
    "s7py.charts",
    "s7py.constants",
    "s7py.db",
    "s7py.log",
    "s7py.plc",
    "s7py.schema",
    "s7py.worker",
    "s7py.backends",
    "s7py.backends.base",
    "s7py.backends.factory",
    "s7py.backends.snap7",
    "s7py.backends.opcua",
    "s7py.opcua_values",
    "s7py.opcua_import",
    "s7py.opcua_connect",
    "s7py.opcua_browse",
    "s7py.ui_opcua_browse",
    "s7py.ui_opcua_schema",
    "s7py.ui_base",
    "s7py.ui_connection",
    "s7py.ui_database",
    "s7py.ui_plot",
    "s7py.ui_schema",
    "s7py.ui_help",
    "s7py.ui_about",
    "s7py.ui_flow",
    "s7py.ui_snap7_schema",
    "s7py.help",
    "s7py.help_pdf",
    "sqlite3",
    "tkinter",
    "tkinter.ttk",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.scrolledtext",
    "tkinter.simpledialog",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "PIL._tkinter_finder",
] + snap7_hiddenimports + mpl_hiddenimports + pil_hiddenimports

a = Analysis(
    [str(ROOT / "s7py.py")],
    pathex=[str(ROOT)],
    binaries=snap7_binaries + mpl_binaries + pil_binaries,
    datas=snap7_datas
    + mpl_datas
    + pil_datas
    + [
        (str(ROOT / "LICENSE"), "."),
        (str(ROOT / "LICENSE_THIRD_PARTY.txt"), "."),
        (str(ROOT / "s7py" / "help"), "s7py/help"),
        (str(ROOT / "docs" / "TIA_OPCUA_S7-1500.md"), "docs"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="s7py",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "packaging" / "build" / "s7py.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="s7py",
)
