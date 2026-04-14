"""
_ocr_capture.py — OCR 截屏取词。

职责单一：截取鼠标周围区域，调用 RapidOCR 识别文字，
根据鼠标相对位置定位最近的英文单词。
不含 UI Automation 逻辑或弹窗逻辑。
"""
import re

from quickdict._word_utils import clean_word, extract_word_at_position
from quickdict.config import logger

# 截图区域：鼠标周围的半宽/半高（像素）
_HALF_W = 120
_HALF_H = 40

# OCR 置信度阈值
_MIN_CONFIDENCE = 0.5

# 结果框到鼠标中心的最大距离（像素），超出则忽略
_MAX_BOX_DISTANCE = 150


class OcrCapture:
    """OCR 截屏取词器（懒加载模型）。"""

    def __init__(self):
        self._ocr = None
        self._available: bool | None = None  # None = 未检测

    # ── 公开接口 ──────────────────────────────────────────

    def capture(self, x: int, y: int) -> str | None:
        """
        截取 (x, y) 周围区域并 OCR 识别，返回鼠标位置处的英文单词。

        如果 RapidOCR 未安装或识别失败，返回 None。
        """
        if not self._ensure_available():
            return None

        img = self._grab_region(x, y)
        if img is None:
            return None

        results = self._recognize(img)
        if not results:
            return None

        # 鼠标在截图中的相对坐标（截图中心）
        return self._pick_word(results, _HALF_W, _HALF_H)

    # ── 懒加载 ────────────────────────────────────────────

    def _ensure_available(self) -> bool:
        """检查并懒加载 OCR 引擎。加载失败后不再重试。"""
        if self._available is False:
            return False
        if self._ocr is not None:
            return True
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
            self._available = True
            logger.info("OCR 引擎已加载")
            return True
        except Exception as e:
            self._available = False
            logger.info("OCR 引擎不可用，跳过 OCR 取词: %s", e)
            return False

    # ── 截图 ──────────────────────────────────────────────

    @staticmethod
    def _grab_region(x: int, y: int):
        """截取鼠标周围区域，返回 PIL Image 或 None。"""
        try:
            from PIL import ImageGrab
            bbox = (x - _HALF_W, y - _HALF_H, x + _HALF_W, y + _HALF_H)
            return ImageGrab.grab(bbox=bbox)
        except Exception:
            return None

    # ── OCR 识别 ──────────────────────────────────────────

    def _recognize(self, img) -> list[tuple] | None:
        """
        调用 RapidOCR 识别图片。

        返回 [(box, text, confidence), ...] 或 None。
        box: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        """
        try:
            result, _ = self._ocr(img)
            return result if result else None
        except Exception:
            return None

    # ── 定位单词 ──────────────────────────────────────────

    @staticmethod
    def _pick_word(results: list[tuple], cursor_rel_x: float,
                   cursor_rel_y: float) -> str | None:
        """
        从 OCR 结果中找到距离鼠标最近的文本框，
        再根据鼠标在框内的相对位置提取对应单词。
        """
        best_word: str | None = None
        best_dist = float("inf")

        for box, text, confidence in results:
            if confidence < _MIN_CONFIDENCE:
                continue

            # 跳过不含英文字母的结果
            if not re.search(r"[a-zA-Z]{2,}", text):
                continue

            # 文本框中心
            cx = sum(p[0] for p in box) / 4
            cy = sum(p[1] for p in box) / 4
            dist = ((cx - cursor_rel_x) ** 2 + (cy - cursor_rel_y) ** 2) ** 0.5

            if dist > _MAX_BOX_DISTANCE or dist >= best_dist:
                continue

            # 鼠标在文本框内的相对 X 位置 → 字符位置
            box_left = min(p[0] for p in box)
            box_right = max(p[0] for p in box)
            box_width = box_right - box_left

            if box_width > 0 and len(text) > 0:
                char_pos = int(
                    (cursor_rel_x - box_left) / box_width * len(text)
                )
                char_pos = max(0, min(char_pos, len(text) - 1))
                raw = extract_word_at_position(text, char_pos)
            else:
                # 框太窄，取整段中第一个英文单词
                m = re.search(r"[a-zA-Z]{2,}", text)
                raw = m.group(0) if m else None

            word = clean_word(raw)
            if word:
                best_dist = dist
                best_word = word

        return best_word
