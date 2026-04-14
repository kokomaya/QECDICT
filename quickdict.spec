# -*- mode: python ; coding: utf-8 -*-
"""
QuickDict PyInstaller 打包配置。

打包命令:
    .venv\Scripts\pyinstaller quickdict.spec

产出结构:
    dist/QuickDict/
        QuickDict.exe
        data/          ← 手动复制 ecdict.db 到这里
"""
import os

block_cipher = None
_ROOT = os.path.abspath(".")

a = Analysis(
    ["quickdict/main.py"],
    pathex=[_ROOT],
    binaries=[],
    datas=[
        # 内置资源：打包进 exe
        ("quickdict/assets/icon.png", "quickdict/assets"),
        ("quickdict/styles/popup.qss", "quickdict/styles"),
        # stardict.py 需要在运行时被 import
        ("stardict.py", "."),
    ],
    hiddenimports=[
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "uiautomation",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大模块（OCR 等后续按需添加）
        "rapidocr_onnxruntime",
        "onnxruntime",
        "pyttsx3",
        "matplotlib",
        "numpy",
        "PIL",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="QuickDict",
    icon="quickdict/assets/icon.png",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 无控制台窗口
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="QuickDict",
)
