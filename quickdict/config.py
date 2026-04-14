# 配置管理（快捷键、主题等）
import json
import logging
import os
import sys

VERSION = "0.1.0"

# ── 冻结/开发 环境检测 ────────────────────────────────────
FROZEN = getattr(sys, "frozen", False)

# ── 日志配置 ──────────────────────────────────────────────
# Release(FROZEN) → 静默；开发 → INFO 级别输出到 stderr
# 根级别设 WARNING 避免第三方库噪音，QuickDict 自己的 logger 单独设级别
logging.basicConfig(
    level=logging.WARNING,
    format="[%(name)s] %(message)s",
)
logger = logging.getLogger("QuickDict")
if FROZEN:
    logging.disable(logging.CRITICAL)
else:
    logger.setLevel(logging.INFO)

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

# ── 用户设置持久化 ────────────────────────────────────────
_SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
_DEFAULTS = {
    "capture_mode": "auto",  # auto / uia / ocr
    "trigger_mode": "hover",  # hover / ctrl
}


def load_settings() -> dict:
    """读取用户设置，文件不存在或损坏时返回默认值。"""
    if os.path.isfile(_SETTINGS_PATH):
        try:
            with open(_SETTINGS_PATH, encoding="utf-8") as f:
                saved = json.load(f)
            # 合并默认值（新增字段自动补全）
            return {**_DEFAULTS, **saved}
        except Exception:
            pass
    return dict(_DEFAULTS)


def save_settings(settings: dict):
    """将用户设置写入 JSON 文件。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


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

    logger.info("首次启动，正在构建词典数据库（约 1-2 分钟）...")
    logger.info("CSV 源: %s", csv_path)

    from quickdict._db_importer import import_csv_to_db
    from quickdict._lemma_builder import build_lemma_table

    os.makedirs(DATA_DIR, exist_ok=True)
    word_count = import_csv_to_db(csv_path, DB_PATH)
    lemma_count = build_lemma_table(DB_PATH)
    logger.info("完成: %d 词条, %d 词形映射", word_count, lemma_count)

    return DB_PATH
