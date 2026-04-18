# -*- mode: python ; coding: utf-8 -*-
"""
MagicMirror PyInstaller 打包配置。

打包命令:
    .venv\Scripts\pyinstaller magicmirror.spec

产出结构:
    dist/MagicMirror/
        MagicMirror.exe
"""
import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None
_ROOT = os.path.abspath(".")
_UPX_DIR = os.path.join(_ROOT, "tools", "upx-4.2.4-win64")

# 收集 rapidocr_onnxruntime 的模型文件
_rapidocr_datas = collect_data_files("rapidocr_onnxruntime", include_py_files=False)

a = Analysis(
    ["magic_mirror/main.py"],
    pathex=[_ROOT],
    binaries=[],
    datas=[
        ("magic_mirror/config/.env", "magic_mirror/config"),
        ("magic_mirror/config/llm_providers.yaml", "magic_mirror/config"),
    ] + _rapidocr_datas,
    hiddenimports=[
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "wordninja",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
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
    name="MagicMirror",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
)

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
    "Qt6WebEngineCore.dll",
]

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=_UPX_EXCLUDE,
    name="MagicMirror",
)
