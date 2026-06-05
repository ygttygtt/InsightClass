# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\insightclass\\web\\launcher.pyw'],
    pathex=[],
    binaries=[],
    datas=[('configs/classes.yaml', 'configs'), ('src/insightclass/web/templates', 'insightclass/web/templates'), ('src/insightclass/web/static', 'insightclass/web/static'), ('experiments/baseline_yolo11n_v2_e80-2/weights/best.pt', 'models')],
    hiddenimports=['insightclass.web.server', 'insightclass.web.model_cache', 'uvicorn', 'torch', 'ultralytics', 'cv2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='InsightClass',
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
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='InsightClass',
)
