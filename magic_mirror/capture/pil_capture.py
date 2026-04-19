"""屏幕截图 — IScreenCapture 的 PIL + dxcam 实现"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
from typing import Tuple

import numpy as np
from PIL import Image, ImageGrab

from magic_mirror.interfaces.types import CaptureResult

logger = logging.getLogger(__name__)

# 像素均值低于此值视为黑屏（硬件加速窗口遮挡）
_BLACK_THRESHOLD = 5


class PilScreenCapture:
    """IScreenCapture 实现 — PIL.ImageGrab 主路径 + dxcam fallback。

    职责单一：给定屏幕矩形区域，返回截图 numpy 数组。
    不涉及 OCR、翻译或 UI 渲染。
    """

    def capture(self, bbox: Tuple[int, int, int, int]) -> CaptureResult:
        """截取指定屏幕区域。

        Args:
            bbox: (x, y, w, h) 屏幕绝对坐标（逻辑像素）。

        Returns:
            CaptureResult: 包含 BGR 格式 numpy 数组和屏幕坐标。
        """
        x, y, w, h = bbox
        pil_bbox = (x, y, x + w, y + h)  # PIL 需要 (left, top, right, bottom)

        image = self._grab_pil(pil_bbox)

        if image is not None and self._is_black_screen(image):
            logger.debug("GDI 截图黑屏，回退 dxcam")
            dxcam_image = self._grab_dxcam(x, y, w, h)
            if dxcam_image is not None:
                image = dxcam_image

        if image is None:
            # 最坏情况：返回黑色占位图
            logger.warning("截图失败，返回空白图像")
            image = np.zeros((h, w, 3), dtype=np.uint8)

        return CaptureResult(image=image, screen_bbox=bbox)

    # ── PIL 主路径 ──

    @staticmethod
    def _grab_pil(pil_bbox: Tuple[int, int, int, int]) -> np.ndarray | None:
        """使用 PIL.ImageGrab (GDI BitBlt) 截图。"""
        try:
            img = ImageGrab.grab(bbox=pil_bbox, all_screens=True)
            # PIL 返回 RGB，转换为 BGR (OpenCV 标准)
            arr = np.array(img)
            return arr[:, :, ::-1].copy()  # RGB → BGR
        except Exception as e:
            logger.debug("PIL 截图失败: %s", e)
            return None

    # ── 黑屏检测 ──

    @staticmethod
    def _is_black_screen(image: np.ndarray) -> bool:
        """检测截图是否为黑屏（硬件加速窗口遮挡）。"""
        return float(image.mean()) < _BLACK_THRESHOLD

    # ── dxcam fallback ──

    @staticmethod
    def _grab_dxcam(x: int, y: int, w: int, h: int) -> np.ndarray | None:
        """使用 dxcam (DXGI Desktop Duplication) 截图。

        适用于硬件加速窗口（Teams、部分浏览器等）。
        自动检测目标显示器并转换为本地坐标。
        """
        try:
            import dxcam

            monitor_idx, mon_left, mon_top = _get_monitor_info(x, y)

            # 全局坐标 → 显示器本地坐标
            local_left = max(0, x - mon_left)
            local_top = max(0, y - mon_top)
            region = (local_left, local_top, local_left + w, local_top + h)

            cam = dxcam.create(output_idx=monitor_idx)
            frame = cam.grab(region=region)
            del cam  # 释放 DXGI 资源

            if frame is None:
                return None

            # dxcam 返回 RGB，转为 BGR
            return frame[:, :, ::-1].copy()
        except Exception as e:
            logger.debug("dxcam 截图失败: %s", e)
            return None


# ── 多显示器工具函数 ──


def _get_monitor_info(x: int, y: int) -> Tuple[int, int, int]:
    """获取坐标所在显示器的 (output_idx, left, top)。

    使用 Win32 EnumDisplayMonitors 枚举所有显示器，
    找到包含 (x, y) 的那个。找不到则返回主显示器 (0, 0, 0)。
    """
    try:
        monitors: list[Tuple[int, int, int, int]] = []

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