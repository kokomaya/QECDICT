# 配置管理（快捷键、主题等）
import os
import sys

VERSION = "0.1.0"

# ── 冻结/开发 环境检测 ────────────────────────────────────
FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    # PyInstaller 打包后: 临时解压目录（内置资源）
    _BUNDLE_DIR = sys._MEIPASS  # type: ignore[attr-defined]
    # exe 所在目录（外置数据）
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))  # quickdict/
    _APP_DIR = os.path.dirname(_BUNDLE_DIR)  # 项目根目录

# ── 路径常量 ──────────────────────────────────────────────
# 内置资源（打包进 exe）
ASSETS_DIR = os.path.join(_BUNDLE_DIR, "quickdict", "assets") if FROZEN else \
             os.path.join(_BUNDLE_DIR, "assets")
STYLES_DIR = os.path.join(_BUNDLE_DIR, "quickdict", "styles") if FROZEN else \
             os.path.join(_BUNDLE_DIR, "styles")

# 外置数据（与 exe 同级 data/ 目录，不打包进 exe）
DATA_DIR = os.path.join(_APP_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "ecdict.db")
DEFAULT_CSV = os.path.join(_APP_DIR, "stardict", "stardict.csv")


def ensure_db() -> str:
    """
    确保词典数据库存在，返回数据库路径。

    - 数据库已存在 → 直接返回路径
    - 数据库不存在但 CSV 在 → 自动构建
    - 两者都不在 → 抛出 FileNotFoundError
    """
    if os.path.exists(DB_PATH):
        return DB_PATH

    # 查找可用的 CSV 文件（优先完整版，回退到基础版）
    csv_candidates = [
        DEFAULT_CSV,
        os.path.join(PROJECT_ROOT, "ecdict.csv"),
    ]
    csv_path = None
    for candidate in csv_candidates:
        if os.path.exists(candidate):
            csv_path = candidate
            break

    if csv_path is None:
        raise FileNotFoundError(
            f"词典数据库不存在且找不到 CSV 源文件。\n"
            f"请将 stardict.csv 放到 {DEFAULT_CSV}\n"
            f"或运行: python -m quickdict.build_db --csv <path>"
        )

    print(f"[QuickDict] 首次启动，正在构建词典数据库（约 1-2 分钟）...")
    print(f"[QuickDict] CSV 源: {csv_path}")

    from quickdict._db_importer import import_csv_to_db
    from quickdict._lemma_builder import build_lemma_table

    os.makedirs(DATA_DIR, exist_ok=True)
    word_count = import_csv_to_db(csv_path, DB_PATH)
    lemma_count = build_lemma_table(DB_PATH)
    print(f"[QuickDict] 完成: {word_count} 词条, {lemma_count} 词形映射")

    return DB_PATH
