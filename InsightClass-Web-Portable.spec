# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for InsightClass Web Portable (onefile mode)."""

import sys
from pathlib import Path

block_cipher = None

# ---- 源码路径 ----
src_root = Path('src')

# ---- 静态资源（打包到内部） ----
web_templates = src_root / 'insightclass' / 'web' / 'templates'
web_static = src_root / 'insightclass' / 'web' / 'static'

# ---- 内置模型 ----
bundled_model = Path('experiments/baseline_yolo11n_v2_e80-2/weights/best.pt')

a = Analysis(
    ['src/insightclass/__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        # Web 模板和静态资源
        (str(web_templates), 'insightclass/web/templates'),
        (str(web_static), 'insightclass/web/static'),
        # 内置模型
        (str(bundled_model), 'models'),
        # 默认配置文件
        ('configs/classes.yaml', 'configs'),
    ],
    hiddenimports=[
        'insightclass.cli',
        'insightclass.web.server',
        'insightclass.web.model_cache',
        'insightclass.backends.ultralytics_backend',
        # uvicorn hidden imports
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
        # PyTorch
        'torch',
        'torch.nn',
        'torch.nn.functional',
        'torchvision',
        # ultralytics
        'ultralytics',
        # HTTPS
        'cryptography',
        # OpenCV
        'cv2',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除训练相关依赖以减小体积
        'supervision',
        'wandb',
        'tensorboard',
        'pandas',
        'scipy',
        # 排除开发工具
        'pytest',
        'IPython',
        'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='InsightClass-Web-Portable',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    icon=None,
)
