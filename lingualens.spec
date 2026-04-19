# -*- mode: python ; coding: utf-8 -*-
"""
LinguaLens PyInstaller 打包配置 (QuickDict + MagicMirror 合体)。

打包命令:
    .venv\Scripts\pyinstaller lingualens.spec

产出结构:
    dist/LinguaLens/
        LinguaLens.exe
        data/          ← 手动复制 ecdict.db 到这里
"""
import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None
_ROOT = os.path.abspath(".")
_UPX_DIR = os.path.join(_ROOT, "tools", "upx-4.2.4-win64")

_rapidocr_datas = collect_data_files("rapidocr_onnxruntime", include_py_files=False)

import wordninja as _wn
_wn_dir = os.path.join(os.path.dirname(os.path.abspath(_wn.__file__)), "wordninja")
_wordninja_datas = [(_wn_dir, "wordninja")]

a = Analysis(
    ["lingualens_main.py"],
    pathex=[_ROOT],
    binaries=[],
    datas=[
        # QuickDict 资源
        ("quickdict/assets/icon.png", "quickdict/assets"),
        ("quickdict/styles/popup.qss", "quickdict/styles"),
        ("stardict.py", "."),
    ] + _rapidocr_datas + _wordninja_datas,
    hiddenimports=[
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "uiautomation",
        "wordninja",
        "markdown.extensions.fenced_code",
        "markdown.extensions.codehilite",
        "markdown.extensions.tables",
        "markdown.extensions.nl2br",
        "markdown.extensions.extra",
        "pygments",
        "pygments.lexers",
        "pygments.formatters",
        "pygments.formatters.html",
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
    name="LinguaLens",
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
    name="LinguaLens",
)
