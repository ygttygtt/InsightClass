# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the InsightClass windowed application.

Excludes PyTorch and ultralytics (use ONNX Runtime for inference).
Bundles ONNX models from models/onnx/. Includes pywebview launcher.
"""

from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

# --- Build data list before Analysis ---
_datas = [
    (str(root / 'configs' / 'classes.yaml'), 'configs'),
    (str(root / 'frontend' / 'dist'), 'frontend/dist'),
    (str(root / 'assets' / 'insightclass.ico'), 'assets'),
    (str(root / 'assets' / 'insightclass-tray.png'), 'assets'),
]

# Bundle ONNX models
for _file in (root / 'models' / 'onnx').glob('*.onnx'):
    _datas.append((str(_file), 'models/onnx'))

a = Analysis(
    ['src/insightclass/web/launcher.pyw'],
    pathex=[str(root / 'src')],
    binaries=[],
    datas=_datas,
    hiddenimports=[
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
        'webview.platforms.winforms',
        'pystray',
        'pystray._win32',
        'onnxruntime',
        'insightclass.web.server',
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
        'cefpython3',
        'IPython',
        'ipykernel',
        'jupyter',
        'sphinx',
        'nbformat',
        'jedi',
        'parso',
        'black',
        'zmq',
        'tkinter',
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
    upx=False,
    console=False,
    icon=str(root / 'assets' / 'insightclass.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='InsightClass',
)
