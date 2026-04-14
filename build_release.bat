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

REM 生成使用说明
(
echo QuickDict v%VER% 使用说明
echo ========================
echo.
echo 【部署步骤】
echo.
echo   1. 解压 QuickDict.zip（程序包）到任意目录
echo   2. 解压 QuickDict-data.zip（数据库包）
echo   3. 将 QuickDict-data\data\ 文件夹复制到 QuickDict\ 下
echo.
echo   最终目录结构：
echo.
echo     QuickDict\
echo       QuickDict.exe        主程序
echo       _internal\           运行时依赖（勿删除）
echo       data\
echo         ecdict.db           词典数据库（~800MB）
echo.
echo   4. 双击 QuickDict.exe 启动
echo.
echo 【使用方式】
echo.
echo   - 连按两次 Ctrl        激活取词模式
echo   - 鼠标悬停在英文单词上  自动弹出翻译卡片
echo   - 按 Esc               退出取词模式
echo   - 右键系统托盘图标      打开菜单
echo     - 开启/关闭取词       控制快捷键监听
echo     - 取词模式            切换 自动/仅UIA/仅OCR
echo     - 退出                关闭程序
echo.
echo 【系统要求】
echo.
echo   - Windows 10 / 11（64 位）
echo   - 无需安装 Python 或其他运行时
echo   - 磁盘空间：程序约 80MB + 数据库约 800MB
echo.
echo 【常见问题】
echo.
echo   Q: 启动后没有窗口？
echo   A: QuickDict 运行在系统托盘，查看屏幕右下角托盘区的蓝色 D 图标。
echo.
echo   Q: 主显示器取词失败，副屏正常？
echo   A: 请在系统设置中确认各显示器的缩放比例一致（推荐 100%% 或 150%%）。
echo.
echo   Q: 图片/PDF 上无法取词？
echo   A: 右键托盘 → 取词模式 → 切换为「仅 OCR」或「自动」。
) > "%RELEASE_DIR%\使用说明.txt"

echo        OK

REM ── 输出结果 ────────────────────────────────────────────
echo [4/4] 打包完成！
echo.
echo   发布目录: %RELEASE_DIR%\
echo.
echo   %APP_DIR%\             ← 程序（分发给用户）
echo     QuickDict.exe
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
