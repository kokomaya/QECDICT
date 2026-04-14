"""
word_capture.py — 屏幕取词模块。

职责单一：获取鼠标位置下的英文单词（通过 Windows UI Automation）。
文本处理逻辑委托给 _word_utils。后续 Task 9 会在此增加 OCR 回退。
"""
import ctypes
import ctypes.wintypes

import uiautomation as uia

from quickdict._word_utils import (
    clean_word,
    estimate_char_position,
    extract_word_at_position,
    first_english_word,
    split_compound,
)


def _get_cursor_pos() -> tuple[int, int]:
    """获取当前鼠标光标的屏幕坐标。"""
    pt = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


class WordCapture:
    """屏幕取词器：获取鼠标位置下的英文单词。"""

    def capture(self) -> str | None:
        """
        获取鼠标当前位置下的英文单词。

        返回清理后的小写单词，或 None。
        """
        x, y = _get_cursor_pos()
        return self._capture_via_uia(x, y)

    def capture_split(self) -> list[str]:
        """
        获取取词结果并拆分驼峰/下划线命名。

        返回拆分后的单词列表（可能为空）。
        """
        word = self.capture()
        if not word:
            return []
        parts = split_compound(word)
        return [w for w in parts if clean_word(w)]

    # ── UI Automation 取词 ────────────────────────────────

    def _capture_via_uia(self, x: int, y: int) -> str | None:
        """通过 Windows UI Automation 获取鼠标下的单词。"""
        try:
            element = uia.ControlFromPoint(x, y)
        except Exception:
            return None

        if element is None:
            return None

        text = self._get_element_text(element)
        if not text or not text.strip():
            return None

        rect = element.BoundingRectangle
        return self._extract_word(text, x, rect)

    @staticmethod
    def _get_element_text(element) -> str | None:
        """
        从 UI 元素中提取文本内容，按优先级尝试多种方式。

        优先级: TextPattern > ValuePattern > Name 属性
        """
        # 方式一：TextPattern（富文本控件：浏览器、编辑器等）
        try:
            pattern = element.GetTextPattern()
            if pattern:
                text = pattern.DocumentRange.GetText(-1)
                if text and text.strip():
                    return text
        except Exception:
            pass

        # 方式二：ValuePattern（输入框、地址栏等）
        try:
            pattern = element.GetValuePattern()
            if pattern:
                text = pattern.Value
                if text and text.strip():
                    return text
        except Exception:
            pass

        # 方式三：Name 属性（通用回退）
        try:
            name = element.Name
            if name and name.strip():
                return name
        except Exception:
            pass

        return None

    @staticmethod
    def _extract_word(text: str, cursor_x: int, rect) -> str | None:
        """从文本中根据鼠标 X 坐标提取对应单词。"""
        elem_width = rect.right - rect.left
        if elem_width <= 0:
            raw = first_english_word(text)
        else:
            char_pos = estimate_char_position(
                cursor_x, rect.left, elem_width, len(text)
            )
            raw = extract_word_at_position(text, char_pos)

        return clean_word(raw)


# ── 独立运行测试 ──────────────────────────────────────────
if __name__ == "__main__":
    import time

    capture = WordCapture()
    print("屏幕取词测试 — 将鼠标悬停在英文文字上")
    print("每秒检测一次，Ctrl+C 终止\n")
    try:
        while True:
            word = capture.capture()
            parts = capture.capture_split()
            if word:
                print(f"  取词: {word!r}  拆分: {parts}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n已退出")
