# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main_watcher.py'],
    pathex=[],
    binaries=[],
    datas=[('client_dictionary.py', '.'), ('ocr_engine.py', '.'), ('validation_ui.py', '.')],
    hiddenimports=['openpyxl', 'watchdog', 'easyocr', 'fitz', 'PIL', 'win10toast', 'rapidfuzz'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='WorkflowFactures',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
