@echo off
chcp 65001 >nul 2>&1

cd /d "%~dp0"

set VER=0.1.0

echo ============================================
echo   LinguaLens Build  v%VER%
echo   (QuickDict + MagicMirror)
echo ============================================
echo.

REM -- check venv
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found, run setup.bat first
    pause
    exit /b 1
)

if not exist "data\ecdict.db" (
    echo [ERROR] data\ecdict.db not found, run setup.bat first
    pause
    exit /b 1
)

if not exist "magic_mirror\config\llm_providers.yaml" (
    echo [ERROR] magic_mirror\config\llm_providers.yaml not found
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

REM -- config
if not exist "magic_mirror\config\.env" (
    echo [WARN] magic_mirror\config\.env not found, creating empty
    echo. > magic_mirror\config\.env
)

REM -- build
echo [2/4] Building LinguaLens.exe (UPX) ...
set PATH=%~dp0tools\upx-4.2.4-win64;%PATH%
.venv\Scripts\pyinstaller lingualens.spec --noconfirm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed
    .venv\Scripts\pyinstaller lingualens.spec --noconfirm
    pause
    exit /b 1
)
echo        OK

REM -- release dir
set RELEASE_DIR=release\LinguaLens-v%VER%
set APP_DIR=%RELEASE_DIR%\LinguaLens
set DB_PKG=%RELEASE_DIR%\LinguaLens-data

echo [3/4] Preparing release dir ...

if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
mkdir "%APP_DIR%"
mkdir "%DB_PKG%\data"

xcopy "dist\LinguaLens\*" "%APP_DIR%\" /e /q /y >nul

copy "data\ecdict.db" "%DB_PKG%\data\ecdict.db" >nul

if exist "使用说明.md" (
    copy "使用说明.md" "%RELEASE_DIR%\使用说明.md" >nul
)

REM -- trim
echo [3.5/4] Trimming ...

for %%f in ("%APP_DIR%\_internal\cv2\opencv_videoio_ffmpeg*.dll") do (
    if exist "%%~f" del /q "%%~f"
)

if exist "%APP_DIR%\_internal\PyQt6\Qt6\translations" (
    rmdir /s /q "%APP_DIR%\_internal\PyQt6\Qt6\translations"
)

if exist "%APP_DIR%\_internal\PyQt6\Qt6\bin\Qt6Pdf.dll" (
    del /q "%APP_DIR%\_internal\PyQt6\Qt6\bin\Qt6Pdf.dll"
)

if exist "%APP_DIR%\_internal\PyQt6\Qt6\plugins\imageformats\qpdf.dll" (
    del /q "%APP_DIR%\_internal\PyQt6\Qt6\plugins\imageformats\qpdf.dll"
)

for %%f in ("%APP_DIR%\_internal\PIL\_avif*.pyd") do (
    if exist "%%~f" del /q "%%~f"
)

if exist "%APP_DIR%\_internal\PyQt6\Qt6\bin\opengl32sw.dll" (
    del /q "%APP_DIR%\_internal\PyQt6\Qt6\bin\opengl32sw.dll"
)

if exist "%APP_DIR%\_internal\PyQt6\Qt6\plugins\imageformats\qwebp.dll" (
    del /q "%APP_DIR%\_internal\PyQt6\Qt6\plugins\imageformats\qwebp.dll"
)
if exist "%APP_DIR%\_internal\PyQt6\Qt6\plugins\imageformats\qtiff.dll" (
    del /q "%APP_DIR%\_internal\PyQt6\Qt6\plugins\imageformats\qtiff.dll"
)

echo        OK

REM -- done
echo [4/4] Done!
echo.
echo   Release: %RELEASE_DIR%\
echo.
echo   %APP_DIR%\              -- app
echo     LinguaLens.exe
echo     _internal\
echo.
echo   %DB_PKG%\               -- database (separate)
echo     data\ecdict.db
echo.
echo   Copy %DB_PKG%\data\ into %APP_DIR%\
echo   Then run LinguaLens.exe
echo.
pause
