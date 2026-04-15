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
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None
_ROOT = os.path.abspath(".")
_UPX_DIR = os.path.join(_ROOT, "tools", "upx-4.2.4-win64")

# 收集 rapidocr_onnxruntime 的模型文件（config.yaml + models/*.onnx）
_rapidocr_datas = collect_data_files("rapidocr_onnxruntime", include_py_files=False)

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
    ] + _rapidocr_datas,
    hiddenimports=[
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "uiautomation",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pyttsx3",
        "matplotlib",
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
    upx_exclude=[],
    console=False,  # 无控制台窗口
    disable_windowed_traceback=False,
)

# UPX 无法安全压缩的文件（某些 C 扩展压缩后会 crash）
_UPX_EXCLUDE = [
    "vcruntime140.dll",
    "ucrtbase.dll",
    "msvcp140.dll",
    "python3.dll",
    "python312.dll",
    "cv2.pyd",
    "onnxruntime.dll",
    "onnxruntime_pybind11_state.pyd",
    "Qt6Core.dll",
    "Qt6Gui.dll",
    "Qt6Widgets.dll",
]

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=_UPX_EXCLUDE,
    name="QuickDict",
)
