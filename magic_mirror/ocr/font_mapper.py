"""字体映射器 — 将 FontInfo 属性映射到系统可用字体。

惰性初始化：首次调用时查询 QFontDatabase 缓存可用字体列表。
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from magic_mirror.config.settings import (
    FONT_FAMILY_EN_SANS,
    FONT_FAMILY_EN_SERIF,
    FONT_FAMILY_ZH,
    FONT_FAMILY_ZH_SERIF,
)
from magic_mirror.interfaces.types import FontInfo

logger = logging.getLogger(__name__)

_available_cache: Optional[Dict[str, bool]] = None

# Fallback 链：每种风格从首选到最终回退
_SERIF_ZH_CHAIN = [FONT_FAMILY_ZH_SERIF, "SimSun", "NSimSun", FONT_FAMILY_ZH]
_SANS_ZH_CHAIN = [FONT_FAMILY_ZH, "SimHei"]
_SERIF_EN_CHAIN = [FONT_FAMILY_EN_SERIF, "Georgia", "Cambria"]
_SANS_EN_CHAIN = [FONT_FAMILY_EN_SANS, "Calibri", "Arial"]


def _ensure_cache() -> Dict[str, bool]:
    global _available_cache
    if _available_cache is not None:
        return _available_cache

    _available_cache = {}
    try:
        from PyQt6.QtGui import QFontDatabase
        families = QFontDatabase.families()
        for f in families:
            _available_cache[f.lower()] = True
        logger.debug("Font cache: %d families", len(_available_cache))
    except Exception as e:
        logger.warning("QFontDatabase not available: %s", e)

    return _available_cache


def _first_available(chain: List[str]) -> str:
    cache = _ensure_cache()
    for name in chain:
        if name.lower() in cache:
            return name
    return chain[-1]


def map_font(
    font_info: FontInfo, target_lang: str = "zh",
) -> Tuple[str, bool, bool]:
    """将字体属性映射到系统字体名称。

    Returns:
        (font_family, should_bold, should_italic)
    """
    if font_info.is_serif:
        if target_lang == "zh":
            family = _first_available(_SERIF_ZH_CHAIN)
        else:
            family = _first_available(_SERIF_EN_CHAIN)
    else:
        if target_lang == "zh":
            family = _first_available(_SANS_ZH_CHAIN)
        else:
            family = _first_available(_SANS_EN_CHAIN)

    return family, font_info.is_bold, font_info.is_italic
