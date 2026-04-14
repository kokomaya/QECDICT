"""
_db_importer.py — 将 ecdict.csv 批量导入 SQLite 数据库。

职责单一：只负责读取 CSV 并写入 stardict 主表。
使用 StarDict 类创建表结构，然后用批量 INSERT 写入数据以获得最佳性能。
"""
import csv
import os
import sqlite3
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from stardict import StarDict, stripword

# CSV 表头与 stardict 表字段的对应关系（不含 id、sw）
_CSV_HEADS = (
    "word", "phonetic", "definition", "translation", "pos",
    "collins", "oxford", "tag", "bnc", "frq",
    "exchange", "detail", "audio",
)

_INT_FIELDS = {"collins", "oxford", "bnc", "frq"}

_BATCH_SIZE = 5000
_LOG_INTERVAL = 50000


def _parse_int(value: str) -> int | None:
    """安全的整数解析，空字符串和非法值返回 None。"""
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _read_csv_rows(csv_path: str):
    """逐行读取 CSV，yield (word, sw, field_values_tuple)。"""
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)  # 跳过表头

        # 确保字段顺序与预期一致
        assert header == list(_CSV_HEADS), f"Unexpected CSV header: {header}"

        seen = set()
        for row in reader:
            if len(row) < 1:
                continue
            # 补齐缺失字段
            while len(row) < len(_CSV_HEADS):
                row.append("")

            word = row[0]
            word_lower = word.lower()
            if word_lower in seen:
                continue
            seen.add(word_lower)

            sw = stripword(word)

            # 构造字段值元组（与 INSERT 语句列顺序一致）
            values = [word, sw]
            for i, name in enumerate(_CSV_HEADS):
                if name == "word":
                    continue  # 已在 values[0]
                raw = row[i] if i < len(row) else ""
                if name in _INT_FIELDS:
                    values.append(_parse_int(raw))
                else:
                    values.append(raw if raw else None)
            yield tuple(values)


def import_csv_to_db(csv_path: str, db_path: str) -> int:
    """
    将 CSV 导入 SQLite 数据库，返回导入的词条数。

    使用 StarDict 类初始化表结构，然后直接用批量 INSERT 写入以获得最佳性能。
    """
    # 1. 用 StarDict 创建表结构和索引
    sd = StarDict(db_path)
    sd.close()

    # 2. 直接操作 SQLite 连接，批量写入
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=OFF;")
    conn.execute("PRAGMA cache_size=-64000;")  # 64MB cache

    # INSERT 列顺序: word, sw, phonetic, definition, translation, pos,
    #                 collins, oxford, tag, bnc, frq, exchange, detail, audio
    insert_sql = """
        INSERT OR IGNORE INTO stardict
            (word, sw, phonetic, definition, translation, pos,
             collins, oxford, tag, bnc, frq, exchange, detail, audio)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    count = 0
    batch = []

    for values in _read_csv_rows(csv_path):
        batch.append(values)
        count += 1

        if len(batch) >= _BATCH_SIZE:
            conn.executemany(insert_sql, batch)
            conn.commit()
            batch.clear()

        if count % _LOG_INTERVAL == 0:
            print(f"       ... {count} words processed")

    # 写入剩余数据
    if batch:
        conn.executemany(insert_sql, batch)
        conn.commit()

    conn.close()
    return count
