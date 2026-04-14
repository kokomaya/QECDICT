"""
build_db.py — 将 ecdict.csv 导入 SQLite 数据库并构建 lemma 反查表。

用法:
    python -m quickdict.build_db                 # 默认导入
    python -m quickdict.build_db --force          # 强制重建
    python -m quickdict.build_db --csv path.csv   # 指定 CSV 路径
"""
import argparse
import csv
import os
import sys
import time

# 将项目根目录加入 sys.path，以便导入 stardict
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from quickdict._db_importer import import_csv_to_db
from quickdict._lemma_builder import build_lemma_table


def _default_csv_path() -> str:
    return os.path.join(_PROJECT_ROOT, "stardict", "stardict.csv")


def _default_db_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ecdict.db")


def main():
    parser = argparse.ArgumentParser(description="Build ecdict.db from ecdict.csv")
    parser.add_argument("--csv", default=_default_csv_path(), help="Path to ecdict.csv")
    parser.add_argument("--db", default=_default_db_path(), help="Output SQLite db path")
    parser.add_argument("--force", action="store_true", help="Force rebuild if db exists")
    args = parser.parse_args()

    if os.path.exists(args.db) and not args.force:
        print(f"[skip] {args.db} already exists. Use --force to rebuild.")
        return

    if not os.path.exists(args.csv):
        print(f"[error] CSV file not found: {args.csv}")
        sys.exit(1)

    os.makedirs(os.path.dirname(args.db), exist_ok=True)

    # 如果强制重建，先删除旧数据库
    if os.path.exists(args.db) and args.force:
        os.remove(args.db)

    t0 = time.time()

    print(f"[1/2] Importing CSV → SQLite ...")
    word_count = import_csv_to_db(args.csv, args.db)
    t1 = time.time()
    print(f"       Done. {word_count} words imported in {t1 - t0:.1f}s")

    print(f"[2/2] Building lemma lookup table ...")
    lemma_count = build_lemma_table(args.db)
    t2 = time.time()
    print(f"       Done. {lemma_count} lemma mappings in {t2 - t1:.1f}s")

    print(f"\nTotal time: {t2 - t0:.1f}s")
    print(f"Database saved to: {args.db}")


if __name__ == "__main__":
    main()
