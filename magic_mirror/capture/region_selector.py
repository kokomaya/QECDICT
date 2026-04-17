"""区域框选 — 全屏半透明遮罩 + 鼠标拖拽矩形框选，纯 UI 组件"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QMouseEvent, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from magic_mirror.config.settings import SELECTOR_BORDER_COLOR, SELECTOR_MASK_COLOR


class RegionSelector(QWidget):
    """全屏遮罩框选器 — 用户拖拽选定屏幕矩形区域。

    Signals:
        sig_region_selected(QRect): 框选完成时发射，携带屏幕绝对坐标。
        sig_cancelled(): 用户按 Esc 取消框选时发射。
    """

    sig_region_selected = pyqtSignal(QRect)
    sig_cancelled = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._origin: QPoint | None = None  # 拖拽起点（窗口坐标）
        self._current: QPoint | None = None  # 拖拽当前位置

        # 从 settings 读取颜色配置
        r, g, b, a = SELECTOR_MASK_COLOR
        self._mask_color = QColor(r, g, b, a)

        br, bg_, bb = SELECTOR_BORDER_COLOR
        self._border_color = QColor(br, bg_, bb)

    # ── 公开方法 ──

    def start(self) -> None:
        """显示全屏遮罩并进入框选状态。"""
        self._origin = None
        self._current = None

        # 合并所有显示器的虚拟桌面几何
        virtual_geo = self._virtual_geometry()
        self.setGeometry(virtual_geo)
        # 不用 showFullScreen()：它会忽略 setGeometry 强制铺满主屏幕
        self.show()
        self.activateWindow()
        self.raise_()

    # ── 鼠标事件 ──

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.pos()
            self._current = event.pos()
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._origin is not None:
            self._current = event.pos()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._origin is not None:
            self._current = event.pos()
            rect = self._selection_rect()

            # 忽略过小的框选（误点）
            if rect is not None and rect.width() > 5 and rect.height() > 5:
                # 窗口坐标 → 屏幕绝对坐标
                screen_rect = QRect(
                    self.mapToGlobal(rect.topLeft()),
                    rect.size(),
                )
                self.hide()
                self.sig_region_selected.emit(screen_rect)
            else:
                # 太小，视为取消
                self._origin = None
                self._current = None
                self.update()

    # ── 键盘事件 ──

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.sig_cancelled.emit()

    # ── 绘制 ──

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self._selection_rect()

        if rect is None:
            # 无框选 — 整屏遮罩
            painter.fillRect(self.rect(), self._mask_color)
        else:
            # 遮罩 + 镂空选区
            full_path = QPainterPath()
            full_path.addRect(self.rect().toRectF())

            selection_path = QPainterPath()
            selection_path.addRect(rect.toRectF())

            mask_path = full_path - selection_path
            painter.fillPath(mask_path, self._mask_color)

            # 选区边框
            pen = QPen(self._border_color, 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(rect)

            # 尺寸标注（选区右下角外侧）
            self._paint_size_label(painter, rect)

        painter.end()

    # ── 私有方法 ──

    def _paint_size_label(self, painter: QPainter, rect: QRect) -> None:
        """在选区右下角外侧绘制 宽×高 尺寸标注。"""
        label = f"{rect.width()} × {rect.height()}"

        font = QFont("Consolas", 11)
        font.setBold(True)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(label)
        text_h = fm.height()
        pad_x, pad_y = 6, 3

        bg_w = text_w + pad_x * 2
        bg_h = text_h + pad_y * 2

        # 定位到选区右下角外侧偏移 4px
        lx = rect.right() - bg_w + 1
        ly = rect.bottom() + 4

        # 防止标签超出窗口底部
        if ly + bg_h > self.height():
            ly = rect.bottom() - bg_h - 4

        painter.setBrush(QColor(0, 0, 0, 180))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(lx, ly, bg_w, bg_h, 4, 4)

        painter.setPen(QColor(255, 255, 255))
        painter.drawText(lx + pad_x, ly + pad_y + fm.ascent(), label)

    def _selection_rect(self) -> QRect | None:
        """根据起点和当前位置计算规范化矩形。"""
        if self._origin is None or self._current is None:
            return None
        return QRect(self._origin, self._current).normalized()

    @staticmethod
    def _virtual_geometry() -> QRect:
        """获取合并所有显示器的虚拟桌面几何。"""
        screen = QApplication.primaryScreen()
        if screen is not None:
            vg = screen.virtualGeometry()
            if vg.isValid():
                return vg
        # 兜底
        return QRect(0, 0, 1920, 1080)