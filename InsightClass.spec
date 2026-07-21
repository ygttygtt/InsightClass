# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for InsightClass — single-folder distribution.

Excludes PyTorch and ultralytics (use ONNX Runtime for inference).
Bundles ONNX models from models/onnx/. Includes pywebview launcher.
"""

import sys
from pathlib import Path

block_cipher = None

# --- Build data list before Analysis ---
_datas = [
    ('configs/classes.yaml', 'configs'),
    ('frontend/dist', 'frontend/dist'),
]

# Bundle ONNX models
import glob as _glob
for _f in _glob.glob('models/onnx/*.onnx'):
    _datas.append((_f, 'models/onnx'))

a = Analysis(
    ['src/insightclass/web/launcher.pyw'],
    pathex=[],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        'engineio.async_drivers.threading',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'multipart',
        'PIL',
        'cv2',
        'yaml',
        'webview',
        'webview.platforms',
        'onnxruntime',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'torch',
        'torchvision',
        'torchaudio',
        'ultralytics',
        'matplotlib',
        'scipy',
        'pandas',
        'tensorboard',
        'mlflow',
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
    console=True,  # keep console for --https cert generation
    icon=None,
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
