"""
_chinese_lookup.py -- 双语互查引擎。

支持中文→英文反查和英文→中文查询：
- 中文关键词：在 translation 字段中搜索匹配的英文词条
- 英文关键词：在 word 字段中搜索匹配的词条（前缀 + 模糊）
按相关度排序后返回结果列表。
"""
import re
import sqlite3
from functools import lru_cache


# 判断是否为纯 ASCII（英文输入）
_RE_ASCII = re.compile(r'^[a-zA-Z][a-zA-Z0-9\s\-]*$')


class ChineseLookup:
    """双语互查引擎（中→英 / 英→中）。"""

    def __init__(self, db_path: str, *, check_same_thread: bool = True):
        self._conn = sqlite3.connect(db_path, check_same_thread=check_same_thread)
        self._conn.execute("PRAGMA query_only=ON;")
        self._conn.row_factory = sqlite3.Row

    def search(self, keyword: str, limit: int = 30) -> list[dict]:
        """
        根据关键词搜索词条，自动判断中英文方向。

        返回按相关度排序的词条列表，每个 dict 包含:
        word, phonetic, translation, definition, collins, bnc, frq, tag, exchange
        """
        keyword = keyword.strip()
        if not keyword:
            return []
        if _RE_ASCII.match(keyword):
            return self._search_english(keyword, limit)
        return self._search_chinese(keyword, limit)

    @lru_cache(maxsize=200)
    def _search_chinese(self, keyword: str, limit: int) -> list[dict]:
        """中文 → 英文：在 translation 字段模糊搜索。"""
        pattern = f"%{keyword}%"
        cursor = self._conn.execute(
            """
            SELECT word, phonetic, translation, definition,
                   collins, oxford, bnc, frq, tag, exchange
            FROM stardict
            WHERE translation LIKE ?
            ORDER BY
                -(CASE WHEN collins IS NULL THEN 0 ELSE collins END),
                CASE WHEN bnc IS NULL OR bnc = 0 THEN 999999 ELSE bnc END,
                LENGTH(word)
            LIMIT ?
            """,
            (pattern, limit),
        )
        return self._rows_to_list(cursor)

    @lru_cache(maxsize=200)
    def _search_english(self, keyword: str, limit: int) -> list[dict]:
        """英文 → 中文：精确匹配 + 前缀匹配 + 模糊匹配。"""
        keyword_lower = keyword.lower()
        prefix_pattern = f"{keyword_lower}%"
        like_pattern = f"%{keyword_lower}%"
        cursor = self._conn.execute(
            """
            SELECT word, phonetic, translation, definition,
                   collins, oxford, bnc, frq, tag, exchange
            FROM stardict
            WHERE word = ? OR word LIKE ? OR word LIKE ?
            ORDER BY
                -- 精确匹配最优先
                CASE WHEN word = ? THEN 0
                     WHEN word LIKE ? THEN 1
                     ELSE 2 END,
                -(CASE WHEN collins IS NULL THEN 0 ELSE collins END),
                CASE WHEN bnc IS NULL OR bnc = 0 THEN 999999 ELSE bnc END,
                LENGTH(word)
            LIMIT ?
            """,
            (keyword_lower, prefix_pattern, like_pattern,
             keyword_lower, prefix_pattern, limit),
        )
        return self._rows_to_list(cursor)

    @staticmethod
    def _rows_to_list(cursor) -> list[dict]:
        results = []
        for row in cursor:
            results.append({
                "word": row["word"],
                "phonetic": row["phonetic"] or "",
                "translation": row["translation"] or "",
                "definition": row["definition"] or "",
                "collins": row["collins"] or 0,
                "oxford": row["oxford"] or 0,
                "bnc": row["bnc"] or 0,
                "frq": row["frq"] or 0,
                "tag": row["tag"] or "",
                "exchange": row["exchange"] or "",
            })
        return results

    def close(self):
        """关闭数据库连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self):
        self.close()
