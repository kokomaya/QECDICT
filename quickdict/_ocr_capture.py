"""
_ocr_capture.py — OCR 截屏取词。

职责单一：截取鼠标周围区域，调用 RapidOCR 识别文字，
根据鼠标相对位置定位最近的英文单词。
不含 UI Automation 逻辑或弹窗逻辑。
"""
import ctypes
import ctypes.wintypes
import re

from quickdict._word_utils import clean_word, extract_word_at_position
from quickdict._ocr_preprocess import preprocess_variants
from quickdict.config import logger

# 截图区域：鼠标周围的半宽/半高（逻辑像素，会根据 DPI 缩放）
_HALF_W = 200
_HALF_H = 80


def set_region_size(half_w: int, half_h: int):
    """动态更新截图区域的半宽/半高。"""
    global _HALF_W, _HALF_H
    _HALF_W = half_w
    _HALF_H = half_h

# OCR 置信度阈值
_MIN_CONFIDENCE = 0.25

# 结果框到鼠标中心的最大距离（像素），超出则忽略
_MAX_BOX_DISTANCE = 200


def _get_screen_scale() -> float:
    """获取主显示器的 DPI 缩放因子（1.0 = 100%, 1.5 = 150%）。"""
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi / 96.0
    except Exception:
        return 1.0


def _get_monitor_info(x: int, y: int) -> tuple[int, int, int]:
    """获取坐标所在显示器的索引和左上角偏移。

    使用 Win32 EnumDisplayMonitors 枚举所有显示器，
    找到包含 (x, y) 的那个，返回 (output_idx, left, top)。
    找不到则默认返回主显示器 (0, 0, 0)。
    """
    try:
        monitors: list[tuple[int, int, int, int]] = []

        def _callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
            r = lprcMonitor.contents
            monitors.append((r.left, r.top, r.right, r.bottom))
            return True

        MONITORENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.wintypes.HMONITOR,
            ctypes.wintypes.HDC,
            ctypes.POINTER(ctypes.wintypes.RECT),
            ctypes.wintypes.LPARAM,
        )
        ctypes.windll.user32.EnumDisplayMonitors(
            None, None, MONITORENUMPROC(_callback), 0,
        )

        for idx, (ml, mt, mr, mb) in enumerate(monitors):
            if ml <= x < mr and mt <= y < mb:
                return idx, ml, mt

    except Exception:
        pass

    return 0, 0, 0


class OcrCapture:
    """OCR 截屏取词器（懒加载模型）。"""

    def __init__(self):
        self._ocr = None
        self._available: bool | None = None  # None = 未检测

    # ── 公开接口 ──────────────────────────────────────────

    def capture(self, x: int, y: int) -> str | None:
        """
        截取 (x, y) 周围区域并 OCR 识别，返回鼠标位置处的英文单词。

        截图一次，生成多种预处理变体，依次识别直到首个有效结果。
        如果 RapidOCR 未安装或所有变体均识别失败，返回 None。
        """
        if not self._ensure_available():
            return None

        img, hw, hh = self._grab_region(x, y)
        if img is None:
            return None

        variants = preprocess_variants(img)
        for idx, variant in enumerate(variants):
            results = self._recognize(variant)
            if not results:
                continue
            word = self._pick_word(results, hw, hh)
            if word:
                logger.debug("OCR 命中变体№%d → %s", idx + 1, word)
                return word

        logger.debug("OCR 所有变体均未命中")
        return None

    def warmup(self):
        """预热 OCR 引擎，降低首次取词延迟。"""
        if not self._ensure_available():
            return
        try:
            import numpy as np
            # 触发一次最小推理，避免首帧模型初始化抖动。
            dummy = np.zeros((8, 8, 3), dtype=np.uint8)
            self._ocr(dummy)
        except Exception:
            pass

    # ── 懒加载 ────────────────────────────────────────────

    def _ensure_available(self) -> bool:
        """检查并懒加载 OCR 引擎。加载失败后不再重试。"""
        if self._available is False:
            return False
        if self._ocr is not None:
            return True
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR(
                det_box_thresh=0.3,
                det_unclip_ratio=2.0,
            )
            self._available = True
            logger.info("OCR 引擎已加载")
            return True
        except Exception as e:
            self._available = False
            logger.info("OCR 引擎不可用，跳过 OCR 取词: %s", e)
            return False

    # ── 截图 ──────────────────────────────────────────────

    _BLACK_THRESHOLD = 5  # 像素均值低于此视为黑屏（硬件加速遮挡）

    @staticmethod
    def _grab_region(x: int, y: int):
        """截取鼠标周围区域（DPI 自适应，多显示器安全）。

        优先使用 PIL.ImageGrab（GDI BitBlt），若截到黑屏
        则回退到 dxcam（DXGI Desktop Duplication），兼容
        Teams 等硬件加速渲染窗口。

        返回 (PIL Image, half_w, half_h) 或 (None, 0, 0)。
        """
        try:
            from PIL import ImageGrab
            import numpy as np

            scale = _get_screen_scale()
            hw = int(_HALF_W * scale)
            hh = int(_HALF_H * scale)
            left = x - hw
            top = y - hh
            right = x + hw
            bottom = y + hh

            # all_screens=True 支持负坐标（多显示器左侧/上方扩展屏）
            img = ImageGrab.grab(bbox=(left, top, right, bottom),
                                all_screens=True)
            arr = np.array(img)

            if arr.mean() > OcrCapture._BLACK_THRESHOLD:
                return img, img.width // 2, img.height // 2

            # GDI 截图黑屏 → 回退 dxcam（DXGI）
            logger.debug("GDI 截图黑屏，回退 dxcam")
            return OcrCapture._grab_region_dxcam(x, y, hw, hh)
        except Exception:
            return None, 0, 0

    @staticmethod
    def _grab_region_dxcam(x: int, y: int, hw: int, hh: int):
        """使用 dxcam (DXGI Desktop Duplication) 截图（多显示器安全）。

        适用于硬件加速渲染窗口（Teams、部分浏览器等）。
        自动检测鼠标所在显示器，转换为显示器本地坐标。
        返回 (PIL Image, half_w, half_h) 或 (None, 0, 0)。
        """
        try:
            import dxcam
            from PIL import Image

            # 检测鼠标所在显示器及其本地坐标偏移
            monitor_idx, mon_left, mon_top = _get_monitor_info(x, y)

            # 全局坐标 → 显示器本地坐标
            local_x = x - mon_left
            local_y = y - mon_top
            region = (
                max(0, local_x - hw),
                max(0, local_y - hh),
                local_x + hw,
                local_y + hh,
            )

            cam = dxcam.create(output_idx=monitor_idx)
            frame = cam.grab(region=region)
            del cam

            if frame is None:
                return None, 0, 0

            img = Image.fromarray(frame)
            return img, img.width // 2, img.height // 2
        except Exception as e:
            logger.debug("dxcam 截图失败: %s", e)
            return None, 0, 0

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
        从 OCR 结果中找到鼠标所在文本框，提取对应单词。

        优先选择光标落入框内的结果；若无，则选加权距离最近的框。
        Y 方向加权 3 倍，确保同行文字优先于上下方文字。
        """
        _Y_WEIGHT = 3.0  # Y 方向距离权重（优先同行）

        best_word: str | None = None
        best_dist = float("inf")

        for box, text, confidence in results:
            if confidence < _MIN_CONFIDENCE:
                continue

            # 跳过不含英文字母的结果
            if not re.search(r"[a-zA-Z]{2,}", text):
                continue

            # 文本框边界
            box_left = min(p[0] for p in box)
            box_right = max(p[0] for p in box)
            box_top = min(p[1] for p in box)
            box_bottom = max(p[1] for p in box)

            # 计算加权距离：光标在框内 → 距离为 0
            dx = max(box_left - cursor_rel_x, 0, cursor_rel_x - box_right)
            dy = max(box_top - cursor_rel_y, 0, cursor_rel_y - box_bottom)
            dist = (dx ** 2 + (dy * _Y_WEIGHT) ** 2) ** 0.5

            if dist > _MAX_BOX_DISTANCE or dist >= best_dist:
                continue

            # 鼠标在文本框内的相对 X 位置 → 字符位置
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
