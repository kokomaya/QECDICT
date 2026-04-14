"""
build_db.py — 将 stardict.csv 导入 SQLite 数据库并构建 lemma 反查表。

用法:
    python -m quickdict.build_db                  # 首次导入（已存在则跳过）
    python -m quickdict.build_db --force           # 强制重建（删除旧库重新导入）
    python -m quickdict.build_db --csv path.csv    # 指定 CSV 源文件
    python -m quickdict.build_db --status          # 查看数据库状态
"""
import argparse
import os
import sqlite3
import sys
import time

from quickdict.config import DB_PATH, DEFAULT_CSV, DATA_DIR
from quickdict._db_importer import import_csv_to_db
from quickdict._lemma_builder import build_lemma_table


def _show_status(db_path: str):
    """打印数据库状态信息。"""
    if not os.path.exists(db_path):
        print(f"[status] 数据库不存在: {db_path}")
        return

    size_mb = os.path.getsize(db_path) / (1024 * 1024)
    conn = sqlite3.connect(db_path)
    word_count = conn.execute("SELECT COUNT(*) FROM stardict").fetchone()[0]
    lemma_count = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='lemma'"
    ).fetchone()[0]
    if lemma_count:
        lemma_count = conn.execute("SELECT COUNT(*) FROM lemma").fetchone()[0]
    conn.close()

    print(f"[status] 数据库路径: {db_path}")
    print(f"[status] 文件大小:   {size_mb:.1f} MB")
    print(f"[status] 词条数:     {word_count:,}")
    print(f"[status] Lemma 映射: {lemma_count:,}")


def main():
    parser = argparse.ArgumentParser(description="Build ecdict.db from stardict.csv")
    parser.add_argument("--csv", default=DEFAULT_CSV, help="Path to source CSV")
    parser.add_argument("--db", default=DB_PATH, help="Output SQLite db path")
    parser.add_argument("--force", action="store_true", help="Force rebuild (delete old db)")
    parser.add_argument("--status", action="store_true", help="Show database status and exit")
    args = parser.parse_args()

    if args.status:
        _show_status(args.db)
        return

    if os.path.exists(args.db) and not args.force:
        print(f"[skip] 数据库已存在: {args.db}")
        print(f"       如需重建请使用: python -m quickdict.build_db --force")
        print(f"       查看状态:       python -m quickdict.build_db --status")
        return

    if not os.path.exists(args.csv):
        print(f"[error] CSV 文件不存在: {args.csv}")
        print(f"        请确认 stardict/stardict.csv 或 ecdict.csv 在项目根目录下")
        sys.exit(1)

    os.makedirs(os.path.dirname(args.db), exist_ok=True)

    # 强制重建时删除旧数据库
    if os.path.exists(args.db):
        os.remove(args.db)
        print(f"[clean] 已删除旧数据库")

    t0 = time.time()

    print(f"[1/2] 导入 CSV → SQLite ...")
    print(f"       源文件: {args.csv}")
    word_count = import_csv_to_db(args.csv, args.db)
    t1 = time.time()
    print(f"       完成: {word_count:,} 词条, 耗时 {t1 - t0:.1f}s")

    print(f"[2/2] 构建 lemma 反查表 ...")
    lemma_count = build_lemma_table(args.db)
    t2 = time.time()
    print(f"       完成: {lemma_count:,} 条映射, 耗时 {t2 - t1:.1f}s")

    print(f"\n总耗时: {t2 - t0:.1f}s")
    print(f"数据库: {args.db}")


if __name__ == "__main__":
    main()
