@echo off
chcp 65001 >nul 2>&1

cd /d "%~dp0"

set VER=0.1.0

echo ============================================
echo   MagicMirror Build  v%VER%
echo ============================================
echo.

REM -- check venv
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found, run setup.bat first
    pause
    exit /b 1
)

REM -- pyinstaller
echo [1/4] Checking PyInstaller ...
.venv\Scripts\pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo        Installing PyInstaller ...
    .venv\Scripts\pip install pyinstaller -q
)
echo        OK

REM -- config files
if not exist "magic_mirror\config\.env" (
    echo [WARN] magic_mirror\config\.env not found, creating empty
    echo. > magic_mirror\config\.env
)
if not exist "magic_mirror\config\llm_providers.yaml" (
    echo [ERROR] magic_mirror\config\llm_providers.yaml not found
    pause
    exit /b 1
)

REM -- build
echo [2/4] Building MagicMirror.exe (UPX) ...
set PATH=%~dp0tools\upx-4.2.4-win64;%PATH%
.venv\Scripts\pyinstaller magicmirror.spec --noconfirm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed
    .venv\Scripts\pyinstaller magicmirror.spec --noconfirm
    pause
    exit /b 1
)
echo        OK

REM -- release dir
set RELEASE_DIR=release\MagicMirror-v%VER%
set APP_DIR=%RELEASE_DIR%\MagicMirror

echo [3/4] Preparing release dir ...

if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
mkdir "%APP_DIR%"

xcopy "dist\MagicMirror\*" "%APP_DIR%\" /e /q /y >nul

REM -- trim: remove unused components
echo [3.5/4] Trimming ...

REM OpenCV video codecs (not needed)
for %%f in ("%APP_DIR%\_internal\cv2\opencv_videoio_ffmpeg*.dll") do (
    if exist "%%~f" del /q "%%~f"
)

REM Qt WebEngine (replaced by QTextBrowser)
if exist "%APP_DIR%\_internal\PyQt6\Qt6\bin\Qt6WebEngineCore.dll" (
    del /q "%APP_DIR%\_internal\PyQt6\Qt6\bin\Qt6WebEngineCore.dll"
)
if exist "%APP_DIR%\_internal\PyQt6\Qt6\bin\QtWebEngineProcess.exe" (
    del /q "%APP_DIR%\_internal\PyQt6\Qt6\bin\QtWebEngineProcess.exe"
)
if exist "%APP_DIR%\_internal\PyQt6\Qt6\resources" (
    rmdir /s /q "%APP_DIR%\_internal\PyQt6\Qt6\resources"
)

REM Qt translations
if exist "%APP_DIR%\_internal\PyQt6\Qt6\translations" (
    rmdir /s /q "%APP_DIR%\_internal\PyQt6\Qt6\translations"
)

REM Qt QML/Quick (not used)
if exist "%APP_DIR%\_internal\PyQt6\Qt6\qml" (
    rmdir /s /q "%APP_DIR%\_internal\PyQt6\Qt6\qml"
)
for %%f in ("%APP_DIR%\_internal\PyQt6\Qt6\bin\Qt6Quick*.dll") do (
    if exist "%%~f" del /q "%%~f"
)
for %%f in ("%APP_DIR%\_internal\PyQt6\Qt6\bin\Qt6Qml*.dll") do (
    if exist "%%~f" del /q "%%~f"
)
if exist "%APP_DIR%\_internal\PyQt6\Qt6\bin\Qt6ShaderTools.dll" (
    del /q "%APP_DIR%\_internal\PyQt6\Qt6\bin\Qt6ShaderTools.dll"
)

REM Qt modules not used
for %%d in (Qt6Pdf Qt6OpenGL Qt6Network Qt6Multimedia Qt6MultimediaWidgets Qt6Positioning Qt6WebChannel opengl32sw Qt6Quick3DPhysics Qt6Quick3DRuntimeRender Qt6Quick3DAssetImport Qt6Quick3DUtils) do (
    if exist "%APP_DIR%\_internal\PyQt6\Qt6\bin\%%d.dll" (
        del /q "%APP_DIR%\_internal\PyQt6\Qt6\bin\%%d.dll"
    )
)

REM Unused image format plugins
for %%d in (qpdf qwebp qtiff) do (
    if exist "%APP_DIR%\_internal\PyQt6\Qt6\plugins\imageformats\%%d.dll" (
        del /q "%APP_DIR%\_internal\PyQt6\Qt6\plugins\imageformats\%%d.dll"
    )
)

REM Unused Qt plugins
for %%d in (position networkinformation) do (
    if exist "%APP_DIR%\_internal\PyQt6\Qt6\plugins\%%d" (
        rmdir /s /q "%APP_DIR%\_internal\PyQt6\Qt6\plugins\%%d"
    )
)

REM Pillow AVIF
for %%f in ("%APP_DIR%\_internal\PIL\_avif*.pyd") do (
    if exist "%%~f" del /q "%%~f"
)

echo        OK

REM -- size report
echo.
echo [4/4] Done!
for /f "tokens=3" %%s in ('dir /s "%APP_DIR%" ^| findstr "File(s)"') do set TOTAL_SIZE=%%s
echo   Total size: %TOTAL_SIZE% bytes
echo.
echo   Release: %RELEASE_DIR%\
echo   Run: %APP_DIR%\MagicMirror.exe
echo.
pause
