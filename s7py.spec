# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spezifikation fuer s7py (Windows .exe)."""

from PyInstaller.utils.hooks import collect_all

block_cipher = None

snap7_datas, snap7_binaries, snap7_hiddenimports = collect_all("snap7")
mpl_datas, mpl_binaries, mpl_hiddenimports = collect_all("matplotlib")

hiddenimports = [
    "s7py",
    "s7py.__main__",
    "s7py.app",
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
    "s7py.opcua_browse",
    "s7py.ui_opcua_browse",
    "s7py.ui_opcua_schema",
    "s7py.ui_base",
    "s7py.ui_connection",
    "s7py.ui_database",
    "s7py.ui_plot",
    "s7py.ui_schema",
    "sqlite3",
    "tkinter",
    "tkinter.ttk",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.scrolledtext",
    "tkinter.simpledialog",
] + snap7_hiddenimports + mpl_hiddenimports

a = Analysis(
    ["s7py.py"],
    pathex=[],
    binaries=snap7_binaries + mpl_binaries,
    datas=snap7_datas + mpl_datas + [("LICENSE", "."), ("LICENSE_THIRD_PARTY.txt", ".")],
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
