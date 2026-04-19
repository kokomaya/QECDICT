# -*- mode: python ; coding: utf-8 -*-
"""
MagicMirror PyInstaller spec.

Build:  .venv\Scripts\pyinstaller magicmirror.spec
Output: dist/MagicMirror/MagicMirror.exe
"""
import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None
_ROOT = os.path.abspath(".")
_UPX_DIR = os.path.join(_ROOT, "tools", "upx-4.2.4-win64")

_rapidocr_datas = collect_data_files("rapidocr_onnxruntime", include_py_files=False)

# wordninja is a single .py file, not a package — manually collect its data
import wordninja as _wn
_wn_dir = os.path.join(os.path.dirname(os.path.abspath(_wn.__file__)), "wordninja")
_wordninja_datas = [(_wn_dir, "wordninja")]

a = Analysis(
    ["magic_mirror/main.py"],
    pathex=[_ROOT],
    binaries=[],
    datas=[
        ("magic_mirror/config/.env", "magic_mirror/config"),
        ("magic_mirror/config/llm_providers.yaml", "magic_mirror/config"),
    ] + _rapidocr_datas + _wordninja_datas,
    hiddenimports=[
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
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
        "matplotlib",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngine",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuick3D",
        "PyQt6.QtOpenGL",
        "PyQt6.QtPdf",
        "PyQt6.QtMultimedia",
    ],
    noarchive=False,
    cipher=block_cipher,
)

# Filter out WebEngine/QML/Quick binaries that slip through excludes
_EXCLUDE_BINS = {
    "Qt6WebEngineCore.dll",
    "Qt6Qml.dll", "Qt6QmlModels.dll", "Qt6QmlWorkerScript.dll",
    "Qt6Quick.dll", "Qt6Quick3D.dll", "Qt6Quick3DRuntimeRender.dll",
    "Qt6Quick3DAssetImport.dll", "Qt6Quick3DUtils.dll", "Qt6Quick3DPhysics.dll",
    "Qt6QuickControls2.dll", "Qt6QuickControls2Basic.dll",
    "Qt6QuickControls2Material.dll", "Qt6QuickControls2Imagine.dll",
    "Qt6QuickControls2Universal.dll", "Qt6QuickDialogs2.dll",
    "Qt6QuickDialogs2QuickImpl.dll", "Qt6QuickDialogs2Utils.dll",
    "Qt6QuickEffects.dll", "Qt6QuickLayouts.dll",
    "Qt6QuickParticles.dll", "Qt6QuickShapes.dll",
    "Qt6QuickTemplates2.dll", "Qt6QuickTest.dll",
    "Qt6QuickTimeline.dll", "Qt6QuickTimelineBlendTrees.dll",
    "Qt6ShaderTools.dll",
    "Qt6Pdf.dll",
    "Qt6OpenGL.dll",
    "Qt6Multimedia.dll", "Qt6MultimediaWidgets.dll",
    "Qt6Network.dll",
    "Qt6Positioning.dll",
    "Qt6WebChannel.dll",
    "opengl32sw.dll",
    "QtWebEngineProcess.exe",
}
a.binaries = [b for b in a.binaries if os.path.basename(b[0]) not in _EXCLUDE_BINS]

# Filter out WebEngine resource/data files
_EXCLUDE_DATA_PREFIXES = (
    "qtwebengine", "icudtl", "v8_context_snapshot",
    "PyQt6/Qt6/qml/", "PyQt6/Qt6/translations/",
    "PyQt6/Qt6/resources/",
)
a.datas = [d for d in a.datas
           if not any(os.path.basename(d[0]).startswith(p) or d[0].replace("\\", "/").startswith(p)
                      for p in _EXCLUDE_DATA_PREFIXES)]

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
