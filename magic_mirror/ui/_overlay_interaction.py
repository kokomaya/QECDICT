"""覆盖层交互行为 — 拖拽移动与边缘缩放。

单一职责：封装鼠标拖拽移动（Alt+左键）和边缘 resize 的输入识别与几何计算，
不涉及渲染、翻译业务或菜单逻辑。
"""

from __future__ import annotations

from enum import IntEnum, auto
from typing import Callable, TYPE_CHECKING

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QCursor, QMouseEvent

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

# resize 手柄热区宽度 (px)
_HANDLE_PX = 6
# 覆盖层最小尺寸
_MIN_W = 50
_MIN_H = 30


class _Edge(IntEnum):
    """边缘 / 角落标识。"""

    NONE = 0
    LEFT = auto()
    RIGHT = auto()
    TOP = auto()
    BOTTOM = auto()
    TOP_LEFT = auto()
    TOP_RIGHT = auto()
    BOTTOM_LEFT = auto()
    BOTTOM_RIGHT = auto()


_CURSOR_MAP = {
    _Edge.LEFT: Qt.CursorShape.SizeHorCursor,
    _Edge.RIGHT: Qt.CursorShape.SizeHorCursor,
    _Edge.TOP: Qt.CursorShape.SizeVerCursor,
    _Edge.BOTTOM: Qt.CursorShape.SizeVerCursor,
    _Edge.TOP_LEFT: Qt.CursorShape.SizeFDiagCursor,
    _Edge.BOTTOM_RIGHT: Qt.CursorShape.SizeFDiagCursor,
    _Edge.TOP_RIGHT: Qt.CursorShape.SizeBDiagCursor,
    _Edge.BOTTOM_LEFT: Qt.CursorShape.SizeBDiagCursor,
}


class OverlayInteraction:
    """封装覆盖层拖拽移动（Alt+左键）与边缘 resize 逻辑。

    由宿主 QWidget 在 mousePressEvent / mouseMoveEvent / mouseReleaseEvent
    中委托调用，返回 ``True`` 表示事件已被消费。
    """

    def __init__(
        self,
        widget: QWidget,
        on_geometry_changed: Callable[[], None] | None = None,
    ) -> None:
        self._w = widget
        self._on_geo_changed = on_geometry_changed
        # drag 状态
        self._dragging = False
        self._drag_offset: QPoint | None = None
        # resize 状态
        self._resizing = False
        self._edge: _Edge = _Edge.NONE
        self._resize_origin: QRect | None = None
        self._resize_anchor: QPoint | None = None

    @property
    def is_interacting(self) -> bool:
        return self._dragging or self._resizing

    # ------------------------------------------------------------------
    # 事件委托
    # ------------------------------------------------------------------

    def on_mouse_press(self, ev: QMouseEvent) -> bool:
        """返回 True 表示启动了拖拽或 resize，事件已消费。"""
        if ev.button() != Qt.MouseButton.LeftButton:
            return False
        # 优先检测 resize（边缘热区）
        edge = _detect_edge(self._w, ev.pos())
        if edge != _Edge.NONE:
            self._resizing = True
            self._edge = edge
            self._resize_anchor = ev.globalPosition().toPoint()
            self._resize_origin = self._w.geometry()
            return True
        # Alt+左键 → 拖拽移动
        if ev.modifiers() & Qt.KeyboardModifier.AltModifier:
            self._dragging = True
            self._drag_offset = ev.globalPosition().toPoint() - self._w.pos()
            return True
        return False

    def on_mouse_move(self, ev: QMouseEvent) -> bool:
        """返回 True 表示正在拖拽/resize，事件已消费。"""
        if self._dragging and self._drag_offset is not None:
            self._w.move(ev.globalPosition().toPoint() - self._drag_offset)
            self._notify()
            return True
        if self._resizing and self._resize_anchor is not None:
            delta = ev.globalPosition().toPoint() - self._resize_anchor
            self._apply_resize(delta)
            self._notify()
            return True
        # 悬停时更新光标形状
        edge = _detect_edge(self._w, ev.pos())
        if edge in _CURSOR_MAP:
            self._w.setCursor(QCursor(_CURSOR_MAP[edge]))
        else:
            self._w.unsetCursor()
        return False

    def on_mouse_release(self, ev: QMouseEvent) -> bool:
        """返回 True 表示拖拽/resize 已结束，事件已消费。"""
        if not self.is_interacting:
            return False
        self._dragging = False
        self._drag_offset = None
        self._resizing = False
        self._edge = _Edge.NONE
        self._resize_origin = None
        self._resize_anchor = None
        return True

    # ------------------------------------------------------------------
    # resize 计算
    # ------------------------------------------------------------------

    def _apply_resize(self, delta: QPoint) -> None:
        g = self._resize_origin
        if g is None:
            return
        x, y, w, h = g.x(), g.y(), g.width(), g.height()
        dx, dy = delta.x(), delta.y()
        e = self._edge
        if e in (_Edge.RIGHT, _Edge.TOP_RIGHT, _Edge.BOTTOM_RIGHT):
            w = max(w + dx, _MIN_W)
        if e in (_Edge.LEFT, _Edge.TOP_LEFT, _Edge.BOTTOM_LEFT):
            nw = max(w - dx, _MIN_W)
            x += w - nw
            w = nw
        if e in (_Edge.BOTTOM, _Edge.BOTTOM_LEFT, _Edge.BOTTOM_RIGHT):
            h = max(h + dy, _MIN_H)
        if e in (_Edge.TOP, _Edge.TOP_LEFT, _Edge.TOP_RIGHT):
            nh = max(h - dy, _MIN_H)
            y += h - nh
            h = nh
        self._w.setGeometry(x, y, w, h)

    def _notify(self) -> None:
        if self._on_geo_changed:
            self._on_geo_changed()


# ------------------------------------------------------------------
# 辅助
# ------------------------------------------------------------------

def _detect_edge(widget: QWidget, pos: QPoint) -> _Edge:
    """检测鼠标位置对应的边缘/角落。"""
    x, y = pos.x(), pos.y()
    w, h = widget.width(), widget.height()
    on_l = x < _HANDLE_PX
    on_r = x > w - _HANDLE_PX
    on_t = y < _HANDLE_PX
    on_b = y > h - _HANDLE_PX
    if on_t and on_l:
        return _Edge.TOP_LEFT
    if on_t and on_r:
        return _Edge.TOP_RIGHT
    if on_b and on_l:
        return _Edge.BOTTOM_LEFT
    if on_b and on_r:
        return _Edge.BOTTOM_RIGHT
    if on_l:
        return _Edge.LEFT
    if on_r:
        return _Edge.RIGHT
    if on_t:
        return _Edge.TOP
    if on_b:
        return _Edge.BOTTOM
    return _Edge.NONE
