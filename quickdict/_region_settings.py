"""
_region_settings.py — 截图区域设置对话框。

纯 PyQt6 实现，无额外依赖。包含尺寸/透明度调节滑块和实时预览面板。
"""

from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QPainterPath, QBrush
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QGroupBox, QWidget, QPushButton,
)


# ── 预览面板 ──────────────────────────────────────────────

class _PreviewPanel(QWidget):
    """缩放预览截图区域在屏幕中的相对大小和透明度效果。"""

    _BG = QColor(40, 40, 50)
    _BORDER_COLOR = QColor(67, 97, 238, 160)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(280, 180)
        self._half_w = 200
        self._half_h = 80
        self._opacity = 15

    def set_params(self, half_w: int, half_h: int, opacity: int):
        self._half_w = half_w
        self._half_h = half_h
        self._opacity = opacity
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 深色背景模拟屏幕
        p.fillRect(self.rect(), self._BG)

        # 缩放: 让最大可能区域 (1000×600) 适配面板
        pw, ph = self.width(), self.height()
        margin = 16
        avail_w, avail_h = pw - margin * 2, ph - margin * 2
        scale = min(avail_w / 1000, avail_h / 600)

        # 截图区域矩形 (居中)
        rw = self._half_w * 2 * scale
        rh = self._half_h * 2 * scale
        rx = (pw - rw) / 2
        ry = (ph - rh) / 2

        # 填充
        fill = QColor(67, 97, 238, self._opacity)
        p.fillRect(QRectF(rx, ry, rw, rh), fill)

        # 虚线边框
        pen = QPen(self._BORDER_COLOR, 2)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRect(QRectF(rx, ry, rw, rh))

        # 中心十字 (鼠标位置)
        cx, cy = pw / 2, ph / 2
        cross = QPen(QColor(255, 80, 80, 200), 1.5)
        p.setPen(cross)
        p.drawLine(int(cx - 8), int(cy), int(cx + 8), int(cy))
        p.drawLine(int(cx), int(cy - 8), int(cx), int(cy + 8))

        # 尺寸标注
        p.setPen(QColor(180, 180, 180))
        p.setFont(QFont("Consolas", 9))
        label = f"{self._half_w * 2} × {self._half_h * 2}"
        p.drawText(QRectF(rx, ry + rh + 2, rw, 20),
                   Qt.AlignmentFlag.AlignCenter, label)

        p.end()


# ── 设置对话框 ────────────────────────────────────────────

class RegionSettingsDialog(QDialog):
    """截图区域设置对话框。

    信号:
        sig_applied(half_w, half_h, opacity): 用户点击确定/应用时发射。
    """

    sig_applied = pyqtSignal(int, int, int)

    _HALF_W_MIN, _HALF_W_MAX = 50, 500
    _HALF_H_MIN, _HALF_H_MAX = 20, 300
    _OPACITY_MIN, _OPACITY_MAX = 0, 200

    def __init__(self, half_w: int = 200, half_h: int = 80, opacity: int = 15,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("截图区域设置")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedWidth(340)

        self._init_half_w = half_w
        self._init_half_h = half_h
        self._init_opacity = opacity

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── 预览 ──
        self._preview = _PreviewPanel()
        layout.addWidget(self._preview)

        # ── 宽度 ──
        grp_size = QGroupBox("区域尺寸（以鼠标为中心）")
        size_layout = QVBoxLayout(grp_size)

        w_row = QHBoxLayout()
        w_row.addWidget(QLabel("总宽:"))
        self._slider_w = QSlider(Qt.Orientation.Horizontal)
        self._slider_w.setRange(self._HALF_W_MIN, self._HALF_W_MAX)
        self._slider_w.setValue(half_w)
        self._slider_w.setSingleStep(10)
        self._slider_w.setPageStep(50)
        w_row.addWidget(self._slider_w, 1)
        self._label_w = QLabel()
        self._label_w.setFixedWidth(52)
        self._label_w.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        w_row.addWidget(self._label_w)
        size_layout.addLayout(w_row)

        # ── 高度 ──
        h_row = QHBoxLayout()
        h_row.addWidget(QLabel("总高:"))
        self._slider_h = QSlider(Qt.Orientation.Horizontal)
        self._slider_h.setRange(self._HALF_H_MIN, self._HALF_H_MAX)
        self._slider_h.setValue(half_h)
        self._slider_h.setSingleStep(5)
        self._slider_h.setPageStep(20)
        h_row.addWidget(self._slider_h, 1)
        self._label_h = QLabel()
        self._label_h.setFixedWidth(52)
        self._label_h.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        h_row.addWidget(self._label_h)
        size_layout.addLayout(h_row)
        layout.addWidget(grp_size)

        # ── 透明度 ──
        grp_op = QGroupBox("填充透明度")
        op_layout = QHBoxLayout(grp_op)
        self._slider_op = QSlider(Qt.Orientation.Horizontal)
        self._slider_op.setRange(self._OPACITY_MIN, self._OPACITY_MAX)
        self._slider_op.setValue(opacity)
        self._slider_op.setSingleStep(5)
        self._slider_op.setPageStep(20)
        op_layout.addWidget(self._slider_op, 1)
        self._label_op = QLabel()
        self._label_op.setFixedWidth(36)
        self._label_op.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        op_layout.addWidget(self._label_op)
        layout.addWidget(grp_op)

        # ── 按钮 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_reset = QPushButton("重置")
        self._btn_ok = QPushButton("确定")
        self._btn_cancel = QPushButton("取消")
        self._btn_ok.setDefault(True)
        btn_row.addWidget(self._btn_reset)
        btn_row.addWidget(self._btn_ok)
        btn_row.addWidget(self._btn_cancel)
        layout.addLayout(btn_row)

        # 连接信号
        self._slider_w.valueChanged.connect(self._on_value_changed)
        self._slider_h.valueChanged.connect(self._on_value_changed)
        self._slider_op.valueChanged.connect(self._on_value_changed)
        self._btn_ok.clicked.connect(self._on_ok)
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_reset.clicked.connect(self._on_reset)

        self._sync_labels()
        self._sync_preview()

    # ── 内部 ──

    def _sync_labels(self):
        hw = self._slider_w.value()
        hh = self._slider_h.value()
        self._label_w.setText(f"{hw * 2} px")
        self._label_h.setText(f"{hh * 2} px")
        self._label_op.setText(str(self._slider_op.value()))

    def _sync_preview(self):
        self._preview.set_params(
            self._slider_w.value(),
            self._slider_h.value(),
            self._slider_op.value(),
        )

    def _on_value_changed(self):
        self._sync_labels()
        self._sync_preview()

    def _on_ok(self):
        self.sig_applied.emit(
            self._slider_w.value(),
            self._slider_h.value(),
            self._slider_op.value(),
        )
        self.accept()

    def _on_reset(self):
        self._slider_w.setValue(self._init_half_w)
        self._slider_h.setValue(self._init_half_h)
        self._slider_op.setValue(self._init_opacity)
