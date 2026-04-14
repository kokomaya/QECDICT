"""
_formatter.py — 词典查询结果的格式化。

职责单一：将 StarDict 原始查询结果转换为 UI 友好的格式化字典。
"""

# ── 标签映射 ──────────────────────────────────────────────
TAG_MAP = {
    "zk": "中考",
    "gk": "高考",
    "cet4": "四级",
    "cet6": "六级",
    "ky": "考研",
    "toefl": "托福",
    "ielts": "雅思",
    "gre": "GRE",
}

# ── 词形变化类型映射 ──────────────────────────────────────
EXCHANGE_TYPE_MAP = {
    "p": "过去式",
    "d": "过去分词",
    "i": "现在分词",
    "3": "三单",
    "r": "比较级",
    "t": "最高级",
    "s": "复数",
    "0": "原形",
    "1": "原形变换类型",
}


def format_collins(value) -> tuple[int, str]:
    """将 collins 字段转换为 (星级整数, 显示字符串)。"""
    stars = int(value) if value else 0
    if stars < 0 or stars > 5:
        stars = 0
    display = "★" * stars + "☆" * (5 - stars) if stars > 0 else ""
    return stars, display


def format_tags(tag_str: str | None) -> tuple[list[str], str]:
    """将 tag 字段解析为 (原始标签列表, 中文显示字符串)。"""
    if not tag_str or not tag_str.strip():
        return [], ""
    raw_tags = tag_str.strip().split()
    display_parts = [TAG_MAP.get(t, t) for t in raw_tags]
    return raw_tags, " ".join(display_parts)


def format_exchange(exchange_str: str | None) -> dict[str, str]:
    """将 exchange 字段解析为 {类型代码: 变换词} 字典，排除 '0' 和 '1' 类型。"""
    if not exchange_str or not exchange_str.strip():
        return {}
    result = {}
    for item in exchange_str.split("/"):
        if ":" not in item:
            continue
        typ, form = item.split(":", 1)
        form = form.strip()
        if typ in ("0", "1") or not form:
            continue
        result[typ] = form
    return result


def format_phonetic(phonetic: str | None) -> str:
    """格式化音标，确保有 / / 包裹。"""
    if not phonetic or not phonetic.strip():
        return ""
    p = phonetic.strip()
    if not p.startswith("/"):
        p = "/" + p
    if not p.endswith("/"):
        p = p + "/"
    return p


def format_result(raw: dict, *, is_lemma_result: bool = False,
                  original_word: str | None = None) -> dict:
    """
    将 StarDict 原始查询结果格式化为 UI 友好的字典。

    Parameters:
        raw: StarDict.query() 返回的原始字典
        is_lemma_result: 是否通过词形还原查到
        original_word: 用户输入的原词（词形还原时使用）
    """
    collins_stars, collins_display = format_collins(raw.get("collins"))
    tags, tag_display = format_tags(raw.get("tag"))
    exchange = format_exchange(raw.get("exchange"))

    return {
        "word": raw.get("word", ""),
        "phonetic": format_phonetic(raw.get("phonetic")),
        "translation": raw.get("translation") or "",
        "definition": raw.get("definition") or "",
        "collins_stars": collins_stars,
        "collins_display": collins_display,
        "oxford": bool(raw.get("oxford")),
        "bnc": raw.get("bnc") or 0,
        "frq": raw.get("frq") or 0,
        "tags": tags,
        "tag_display": tag_display,
        "exchange": exchange,
        "is_lemma_result": is_lemma_result,
        "original_word": original_word,
    }
