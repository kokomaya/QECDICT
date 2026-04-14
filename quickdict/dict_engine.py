"""
dict_engine.py — 词典查询引擎。

职责单一：执行多级回退查询并返回格式化结果。
查询策略: 精确匹配 → lemma 词形还原 → strip 模糊匹配 → 前缀候选。
"""
import os
import sqlite3
import sys
from functools import lru_cache

from quickdict.config import FROZEN

if FROZEN:
    _STARDICT_DIR = sys._MEIPASS  # type: ignore[attr-defined]
else:
    _STARDICT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if _STARDICT_DIR not in sys.path:
    sys.path.insert(0, _STARDICT_DIR)

from stardict import StarDict, stripword
from quickdict._formatter import format_result


class DictEngine:
    """封装 ECDICT 查询逻辑的词典引擎。"""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._sd = StarDict(db_path)
        # 独立连接用于 lemma 查询（StarDict 内部连接不暴露）
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA query_only=ON;")
        self._has_lemma = self._check_lemma_table()

    def _check_lemma_table(self) -> bool:
        """检查 lemma 表是否存在。"""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='lemma'"
        ).fetchone()
        return row[0] > 0

    # ── 核心查询 ──────────────────────────────────────────

    def lookup(self, word: str) -> dict | None:
        """
        查询单词，返回格式化结果。

        查询策略按优先级依次回退:
          1. 精确匹配
          2. lemma 反查表词形还原
          3. stripword 模糊匹配
          4. 返回 None（调用方可用 match_candidates 获取候选）
        """
        if not word or not word.strip():
            return None
        word = word.strip()
        return self._lookup_cached(word)

    @lru_cache(maxsize=500)
    def _lookup_cached(self, word: str) -> dict | None:
        """带 LRU 缓存的查询实现。"""
        # ① 精确匹配
        raw = self._sd.query(word)
        if raw:
            return format_result(raw)

        # ② Lemma 词形还原
        result = self._lookup_via_lemma(word)
        if result:
            return result

        # ③ Strip 模糊匹配
        result = self._lookup_via_strip(word)
        if result:
            return result

        return None

    def _lookup_via_lemma(self, word: str) -> dict | None:
        """通过 lemma 反查表还原词形后查询。"""
        if not self._has_lemma:
            return None
        rows = self._conn.execute(
            "SELECT DISTINCT lemma FROM lemma WHERE variant = ? COLLATE NOCASE",
            (word,),
        ).fetchall()
        for (lemma_word,) in rows:
            # 跳过自引用
            if lemma_word.lower() == word.lower():
                continue
            raw = self._sd.query(lemma_word)
            if raw:
                return format_result(
                    raw, is_lemma_result=True, original_word=word
                )
        return None

    def _lookup_via_strip(self, word: str) -> dict | None:
        """去除非字母数字字符后尝试匹配。"""
        sw = stripword(word)
        if not sw or sw == word.lower():
            return None
        # 通过 sw 字段查 stardict 表
        row = self._conn.execute(
            "SELECT word FROM stardict WHERE sw = ? COLLATE NOCASE LIMIT 1",
            (sw,),
        ).fetchone()
        if row:
            raw = self._sd.query(row[0])
            if raw:
                return format_result(raw)
        return None

    # ── 候选词匹配 ───────────────────────────────────────

    def match_candidates(self, word: str, limit: int = 5) -> list[str]:
        """返回前缀匹配的候选词列表。"""
        if not word or not word.strip():
            return []
        matches = self._sd.match(word.strip(), limit=limit)
        return [w for _, w in matches]

    # ── 生命周期 ──────────────────────────────────────────

    def close(self):
        """关闭数据库连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None
        if self._sd:
            self._sd.close()
            self._sd = None

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
