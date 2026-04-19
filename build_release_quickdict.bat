@echo off
chcp 65001 >nul 2>&1

cd /d "%~dp0"

REM -- read version
for /f "tokens=*" %%v in ('.venv\Scripts\python -c "from quickdict.config import VERSION; print(VERSION)"') do set VER=%%v

echo ============================================
echo   QuickDict Build  v%VER%
echo ============================================
echo.

REM -- best-effort cleanup of running processes that may lock release files
echo [0/4] Stopping running QuickDict processes (if any) ...
taskkill /f /im QuickDict.exe >nul 2>&1
taskkill /f /im LinguaLens.exe >nul 2>&1
echo        OK

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

REM -- pyinstaller
echo [1/4] Checking PyInstaller ...
.venv\Scripts\pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo        Installing PyInstaller ...
    .venv\Scripts\pip install pyinstaller -q
)
echo        OK

REM -- build
echo [2/4] Building QuickDict.exe (UPX) ...
set PATH=%~dp0tools\upx-4.2.4-win64;%PATH%
.venv\Scripts\pyinstaller quickdict.spec --noconfirm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed
    .venv\Scripts\pyinstaller quickdict.spec --noconfirm
    pause
    exit /b 1
)
echo        OK

REM -- release dir
set RELEASE_DIR=release\v%VER%

echo [3/4] Preparing release dir (v%VER%) ...

if exist "%RELEASE_DIR%" (
    rmdir /s /q "%RELEASE_DIR%"
    if exist "%RELEASE_DIR%" (
        echo [WARN] Cannot clean %RELEASE_DIR% because files are still in use.
        for /f %%t in ('powershell -NoProfile -Command "(Get-Date).ToString(\"yyyyMMdd-HHmmss\")"') do set BUILD_TS=%%t
        set RELEASE_DIR=release\v%VER%_%BUILD_TS%
        echo [WARN] Fallback release dir: %RELEASE_DIR%
    )
)

set APP_DIR=%RELEASE_DIR%\QuickDict
set DB_PKG=%RELEASE_DIR%\QuickDict-data
mkdir "%APP_DIR%"
mkdir "%DB_PKG%\data"

xcopy "dist\QuickDict\*" "%APP_DIR%\" /e /q /y >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy build output into %APP_DIR%
    echo         Please make sure release files are not locked by another process.
    pause
    exit /b 1
)

copy "data\ecdict.db" "%DB_PKG%\data\ecdict.db" >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy data\ecdict.db
    echo         The database file may be locked by a running app.
    pause
    exit /b 1
)

if exist "quickdict\使用说明.md" (
    copy "quickdict\使用说明.md" "%RELEASE_DIR%\使用说明.md" >nul
) else if exist "quickdict\README.md" (
    copy "quickdict\README.md" "%RELEASE_DIR%\README.md" >nul
) else (
    echo [WARN] No guide markdown found in quickdict\
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

if exist "%APP_DIR%\_internal\PyQt6\Qt6\bin\Qt6Network.dll" (
    del /q "%APP_DIR%\_internal\PyQt6\Qt6\bin\Qt6Network.dll"
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
echo     QuickDict.exe
echo     _internal\
echo.
echo   %DB_PKG%\               -- database (separate)
echo     data\ecdict.db
echo.
echo   Copy %DB_PKG%\data\ into %APP_DIR%\
echo   Then run QuickDict.exe
echo.
pause
