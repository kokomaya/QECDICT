@echo off
chcp 65001 >nul

cd /d "%~dp0"

REM ── 读取版本号 ──────────────────────────────────────────
for /f "tokens=*" %%v in ('.venv\Scripts\python -c "from quickdict.config import VERSION; print(VERSION)"') do set VER=%%v

echo ============================================
echo   QuickDict 一键打包  v%VER%
echo ============================================
echo.

REM ── 前置检查 ────────────────────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境，请先运行 setup.bat
    pause
    exit /b 1
)

if not exist "data\ecdict.db" (
    echo [错误] 未找到 data\ecdict.db，请先运行 setup.bat 构建数据库
    pause
    exit /b 1
)

REM ── 安装 PyInstaller ────────────────────────────────────
echo [1/4] 检查 PyInstaller ...
.venv\Scripts\pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo        安装 PyInstaller ...
    .venv\Scripts\pip install pyinstaller -q
)
echo        OK

REM ── 执行打包 ────────────────────────────────────────────
echo [2/4] 打包 QuickDict.exe ...
.venv\Scripts\pyinstaller quickdict.spec --noconfirm >nul 2>&1
if errorlevel 1 (
    echo [错误] PyInstaller 打包失败
    .venv\Scripts\pyinstaller quickdict.spec --noconfirm
    pause
    exit /b 1
)
echo        OK

REM ── 准备发布目录 ────────────────────────────────────────
set RELEASE_DIR=release\v%VER%
set APP_DIR=%RELEASE_DIR%\QuickDict
set DB_PKG=%RELEASE_DIR%\QuickDict-data

echo [3/4] 整理发布目录 (v%VER%) ...

if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
mkdir "%APP_DIR%"
mkdir "%DB_PKG%\data"

REM 复制程序（exe + _internal）
xcopy "dist\QuickDict\*" "%APP_DIR%\" /e /q /y >nul

REM DB 单独打包到另一个目录
copy "data\ecdict.db" "%DB_PKG%\data\ecdict.db" >nul

REM 复制 Markdown 使用说明
if not exist "使用说明.md" (
    echo [错误] 未找到 使用说明.md
    pause
    exit /b 1
)
copy "使用说明.md" "%RELEASE_DIR%\使用说明.md" >nul

echo        OK

REM ── 输出结果 ────────────────────────────────────────────
echo [4/4] 打包完成！
echo.
echo   发布目录: %RELEASE_DIR%\
echo.
echo   %APP_DIR%\             ← 程序（分发给用户）
echo     QuickDict.exe
echo     使用说明.md
echo     _internal\
echo.
echo   %DB_PKG%\              ← 数据库（单独分发）
echo     data\ecdict.db
echo.
echo   使用方式:
echo     将 %DB_PKG%\data\ 复制到 %APP_DIR%\ 下
echo     双击 QuickDict.exe 即可运行
echo.
pause
