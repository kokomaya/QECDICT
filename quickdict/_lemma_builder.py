"""
_lemma_builder.py — 从 stardict 表的 exchange 字段构建 lemma 反查表。

职责单一：只负责解析 exchange 字段并写入 lemma 表。

exchange 字段格式示例:
    "d:perceived/p:perceived/3:perceives/i:perceiving"
    "0:perceive"  (表示当前词的原形是 perceive)

类型说明:
    0 — 当前词的原形 (Lemma)
    p — 过去式      d — 过去分词    i — 现在分词
    3 — 第三人称单数  r — 比较级      t — 最高级
    s — 名词复数    1 — Lemma 变换类型
"""
import sqlite3

_BATCH_SIZE = 5000

_CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS lemma (
        variant TEXT NOT NULL,
        lemma   TEXT NOT NULL
    );
"""

_CREATE_INDEX_SQL = """
    CREATE INDEX IF NOT EXISTS idx_lemma_variant ON lemma(variant COLLATE NOCASE);
"""


def _parse_exchange(word: str, exchange: str):
    """
    解析 exchange 字段，yield (variant, lemma) 元组。

    - 类型 "0": 当前 word 是变形，exchange 值是其原形
      → yield (word, 原形)
    - 其他类型: exchange 值是 word 的某种变形
      → yield (变形, word)
    """
    if not exchange:
        return
    for item in exchange.split("/"):
        if ":" not in item:
            continue
        typ, form = item.split(":", 1)
        form = form.strip()
        if not form:
            continue
        if typ == "0":
            # word 的原形是 form
            yield (word, form)
        elif typ != "1":
            # form 是 word 的某种变形，word 是原形
            yield (form, word)


def build_lemma_table(db_path: str) -> int:
    """
    从 stardict 表读取 exchange 字段，构建 lemma 反查表。
    返回写入的映射条数。
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=OFF;")

    # 创建 lemma 表（如已存在则清空重建）
    conn.execute("DROP TABLE IF EXISTS lemma;")
    conn.executescript(_CREATE_TABLE_SQL)

    insert_sql = "INSERT INTO lemma (variant, lemma) VALUES (?, ?);"

    # 读取所有带 exchange 的词条，去重后写入
    cursor = conn.execute(
        "SELECT word, exchange FROM stardict WHERE exchange IS NOT NULL AND exchange != '';"
    )

    seen: set[tuple[str, str]] = set()
    count = 0
    batch: list[tuple[str, str]] = []

    for word, exchange in cursor:
        for variant, lemma in _parse_exchange(word, exchange):
            key = (variant.lower(), lemma.lower())
            if key in seen:
                continue
            seen.add(key)
            batch.append((variant, lemma))
            count += 1
            if len(batch) >= _BATCH_SIZE:
                conn.executemany(insert_sql, batch)
                conn.commit()
                batch.clear()

    if batch:
        conn.executemany(insert_sql, batch)
        conn.commit()

    # 创建索引（数据写入完毕后建索引更快）
    conn.executescript(_CREATE_INDEX_SQL)
    conn.commit()
    conn.close()
    return count
