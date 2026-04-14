"""
_word_utils.py — 单词提取与清理的纯文本处理工具。

职责单一：从文本中定位、提取、清理英文单词。不含任何 UI 或系统调用。
"""
import re

# 匹配合法英文单词：纯字母，或含连字符的复合词（如 self-aware）
_VALID_WORD_RE = re.compile(r"^[a-zA-Z](?:[a-zA-Z\-]*[a-zA-Z])?$")

# camelCase / PascalCase 拆分
_CAMEL_SPLIT_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\b)|[A-Z]+$")


def clean_word(word: str | None) -> str | None:
    """
    清理并验证单词。

    - 去除首尾空白
    - 过滤纯数字、特殊符号
    - 单字母只保留 I / a / A
    - 返回小写形式，无效返回 None
    """
    if not word:
        return None
    word = word.strip()
    if not word:
        return None
    if not _VALID_WORD_RE.match(word):
        return None
    if len(word) == 1 and word.lower() not in ("i", "a"):
        return None
    return word.lower()


def split_compound(word: str) -> list[str]:
    """
    拆分驼峰或下划线命名为独立单词。

    - snake_case  → ["snake", "case"]
    - camelCase   → ["camel", "Case"]  → 各自 lower
    - PascalCase  → ["Pascal", "Case"] → 各自 lower
    - 普通单词   → [word]
    """
    if "_" in word:
        return [w.lower() for w in word.split("_") if w]

    parts = _CAMEL_SPLIT_RE.findall(word)
    if len(parts) > 1:
        return [p.lower() for p in parts]

    return [word.lower()]


def extract_word_at_position(text: str, char_pos: int) -> str | None:
    """
    从文本中提取 char_pos 位置所在的英文单词。

    从 char_pos 向两侧扩展，找到由字母组成的连续片段。
    如果当前位置不是字母，最多向两侧搜索 3 个字符，避免空白区域误取远处单词。
    """
    if not text:
        return None
    char_pos = max(0, min(char_pos, len(text) - 1))

    _MAX_SEARCH_RADIUS = 3  # 最大搜索半径（字符数）

    # 如果当前位置不是字母，向两侧搜索最近的字母（限距离）
    if not text[char_pos].isalpha():
        left = char_pos - 1
        right = char_pos + 1
        found = False
        for _ in range(_MAX_SEARCH_RADIUS):
            if left >= 0 and text[left].isalpha():
                char_pos = left
                found = True
                break
            if right < len(text) and text[right].isalpha():
                char_pos = right
                found = True
                break
            left -= 1
            right += 1
        if not found:
            return None

    # 向左扩展到单词开头
    start = char_pos
    while start > 0 and text[start - 1].isalpha():
        start -= 1

    # 向右扩展到单词结尾
    end = char_pos + 1
    while end < len(text) and text[end].isalpha():
        end += 1

    return text[start:end] if start < end else None


def estimate_char_position(cursor_x: int, elem_left: int, elem_width: int,
                           text_len: int) -> int:
    """
    根据鼠标 X 坐标和元素边界估算文本中的字符位置（等宽假设）。
    """
    if elem_width <= 0 or text_len <= 0:
        return 0
    ratio = (cursor_x - elem_left) / elem_width
    ratio = max(0.0, min(1.0, ratio))
    return int(ratio * (text_len - 1))


def first_english_word(text: str) -> str | None:
    """从文本中提取第一个英文单词。"""
    if not text:
        return None
    match = re.search(r"[a-zA-Z]{2,}", text)
    return match.group(0) if match else None
