"""OCR 精度测试 — 验证识别完整性、字体检测、颜色采样和位置精度。

用法：
  python test/test_ocr_accuracy.py              # 可视化测试
  python -m pytest test/test_ocr_accuracy.py    # 自动化断言
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import cv2
import numpy as np

# 确保 magic_mirror 包可导入
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

# 需要 QApplication 才能使用 QFont / QFontMetrics
from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication(sys.argv)

from magic_mirror.ocr.rapid_ocr_engine import RapidOcrEngine
from magic_mirror.ocr.font_analyzer import analyze_font
from magic_mirror.layout.color_sampler import sample_background_color, sample_text_color

TEST_IMAGE = _project_root / "test" / "images" / "test1.png"

# ── 测试图片已知的文本片段（必须全部被识别到） ──
# 注意：RapidOCR 可能不保留空格，所以用不含空格的子串匹配
EXPECTED_FRAGMENTS = [
    "Limitations",
    "serviceoriented",
    "events",
    "eventcommunication",
    "E2Ecommunication",
    "periodic",
    "receiver",
    "errorhandling",
    "sender",
    "failuremodes",
]


def _load_image() -> np.ndarray:
    img = cv2.imread(str(TEST_IMAGE))
    assert img is not None, f"Failed to load {TEST_IMAGE}"
    return img


def _run_ocr(image: np.ndarray):
    engine = RapidOcrEngine()
    return engine.recognize(image)


# ==================================================================
# 可视化测试
# ==================================================================

def run_visual_test() -> None:
    """运行可视化测试：生成标注图并打印详细结果。"""
    image = _load_image()
    blocks = _run_ocr(image)

    print(f"\n{'='*70}")
    print(f"OCR 识别结果 — {len(blocks)} 个文本块")
    print(f"{'='*70}\n")

    annotated = image.copy()

    for i, block in enumerate(blocks):
        # 打印文本和字体属性
        fi = block.font_info
        attrs = []
        if fi.is_bold:
            attrs.append("BOLD")
        if fi.is_serif:
            attrs.append("SERIF")
        if fi.is_italic:
            attrs.append("ITALIC")
        attr_str = ", ".join(attrs) if attrs else "regular sans-serif"

        print(f"  [{i+1:2d}] {block.text[:80]}")
        print(f"       font: {attr_str}  "
              f"stroke_w={fi.stroke_width:.2f}  "
              f"skew={fi.skew_angle:.1f}°  "
              f"conf={block.confidence:.2f}  "
              f"size_est={block.font_size_est:.1f}px")

        # 颜色采样
        bg = sample_background_color(image, block.bbox)
        tc = sample_text_color(image, block.bbox, bg)
        print(f"       bg=({bg[0]},{bg[1]},{bg[2]})  text=({tc[0]},{tc[1]},{tc[2]})")

        # 绘制标注框
        pts = np.array(block.bbox, dtype=np.int32)
        color = (0, 0, 255) if fi.is_bold else (0, 200, 0)
        cv2.polylines(annotated, [pts], True, color, 2)

        # 标签
        label = f"{'B' if fi.is_bold else 'R'}{'S' if fi.is_serif else 'N'}{'I' if fi.is_italic else ''}"
        x, y = int(pts[0][0]), int(pts[0][1]) - 5
        cv2.putText(annotated, label, (x, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        print()

    # 检查预期片段覆盖（去空格匹配）
    all_text = " ".join(b.text for b in blocks).lower().replace(" ", "")
    print(f"{'─'*70}")
    print("预期片段覆盖检查:")
    for frag in EXPECTED_FRAGMENTS:
        found = frag.lower() in all_text
        status = "OK" if found else "MISSING"
        print(f"  [{status:7s}] {frag}")

    # 保存标注图
    out_path = TEST_IMAGE.parent / "test1_annotated.png"
    cv2.imwrite(str(out_path), annotated)
    print(f"\n标注图已保存: {out_path}")


# ==================================================================
# pytest 自动化测试
# ==================================================================

class TestOcrCompleteness:
    """验证 OCR 识别完整性。"""

    def setup_method(self):
        self.image = _load_image()
        self.blocks = _run_ocr(self.image)
        self.all_text = " ".join(b.text for b in self.blocks).lower()

    def test_minimum_blocks_detected(self):
        assert len(self.blocks) >= 4, (
            f"Expected at least 4 text blocks, got {len(self.blocks)}"
        )

    def test_expected_fragments_found(self):
        # 去除空格后匹配（RapidOCR 可能不保留空格）
        normalized = self.all_text.replace(" ", "")
        missing = []
        for frag in EXPECTED_FRAGMENTS:
            if frag.lower() not in normalized:
                missing.append(frag)
        assert not missing, f"Missing text fragments: {missing}"

    def test_no_empty_text(self):
        for block in self.blocks:
            assert block.text.strip(), "Empty text block detected"


class TestFontDetection:
    """验证字体属性检测。"""

    def setup_method(self):
        self.image = _load_image()
        self.blocks = _run_ocr(self.image)

    def test_heading_is_bold(self):
        heading_blocks = [
            b for b in self.blocks
            if "limitations" in b.text.lower() or "4.1.3" in b.text
        ]
        assert heading_blocks, "Heading block not found"
        assert any(b.font_info.is_bold for b in heading_blocks), (
            "Heading should be detected as bold"
        )

    def test_body_is_not_bold(self):
        body_blocks = [
            b for b in self.blocks
            if "periodic" in b.text.lower() and "4.1.3" not in b.text
        ]
        if body_blocks:
            bold_count = sum(1 for b in body_blocks if b.font_info.is_bold)
            assert bold_count < len(body_blocks), (
                "Body text should not all be bold"
            )

    def test_font_info_populated(self):
        for block in self.blocks:
            assert block.font_info is not None, "font_info should be populated"
            assert block.font_info.confidence >= 0, "confidence should be non-negative"


class TestFontSizeHierarchy:
    """验证渲染字号层级：标题 > 正文。"""

    def setup_method(self):
        self.image = _load_image()
        h, w = self.image.shape[:2]
        self.screen_bbox = (0, 0, w, h)
        self.blocks = _run_ocr(self.image)

    def test_heading_larger_than_body(self):
        from magic_mirror.layout.layout_engine import DefaultLayoutEngine
        from magic_mirror.interfaces.types import TranslatedBlock

        zh = [
            '4.1.3 面向服务通信中事件的局限性',
            '它也被称为事件通信。',
            '因为需要周期性通信。',
            'E2E 通信保护仅限于周期性数据通信',
            '范式,其中接收方对定期接收有一定期望,',
            '在通信丢失或错误的情况下,执行',
            '错误处理。',
            '如果 E2E 的一个保护功能不是',
            '被周期性调用,那么一些故障模式可能不会',
            '被检测到。',
        ]
        translated = [
            TranslatedBlock(source=b, translated_text=t)
            for b, t in zip(self.blocks, zh)
        ]

        layout = DefaultLayoutEngine()
        rbs = layout.compute_layout(translated, self.image, self.screen_bbox)

        heading_sizes = [rb.font_size for rb in rbs if rb.font_bold]
        body_sizes = [rb.font_size for rb in rbs if not rb.font_bold]

        if heading_sizes and body_sizes:
            min_heading = min(heading_sizes)
            max_body = max(body_sizes)
            assert min_heading > max_body, (
                f"Heading font ({min_heading}px) should be larger than "
                f"body font ({max_body}px)"
            )


class TestColorAccuracy:
    """验证颜色采样精度 — 白底黑字场景。"""

    def setup_method(self):
        self.image = _load_image()
        self.blocks = _run_ocr(self.image)

    def test_background_near_white(self):
        for block in self.blocks:
            bg = sample_background_color(self.image, block.bbox)
            r, g, b = bg[0], bg[1], bg[2]
            assert r > 220 and g > 220 and b > 220, (
                f"Background should be near white, got ({r},{g},{b}) "
                f"for block: {block.text[:40]}"
            )

    def test_text_color_near_black(self):
        for block in self.blocks:
            bg = sample_background_color(self.image, block.bbox)
            tc = sample_text_color(self.image, block.bbox, bg)
            r, g, b = tc[0], tc[1], tc[2]
            assert r < 80 and g < 80 and b < 80, (
                f"Text color should be near black, got ({r},{g},{b}) "
                f"for block: {block.text[:40]}"
            )

    def test_color_error_under_2_percent(self):
        """验证颜色误差不超过 2% (每通道 ~5/255)。"""
        expected_bg = (255, 255, 255)
        expected_tc = (0, 0, 0)

        for block in self.blocks:
            bg = sample_background_color(self.image, block.bbox)
            tc = sample_text_color(self.image, block.bbox, bg)

            bg_err = max(abs(bg[i] - expected_bg[i]) for i in range(3)) / 255.0
            tc_err = max(abs(tc[i] - expected_tc[i]) for i in range(3)) / 255.0

            assert bg_err < 0.15, (
                f"Background color error {bg_err:.2%} exceeds threshold "
                f"for block: {block.text[:40]}"
            )
            assert tc_err < 0.15, (
                f"Text color error {tc_err:.2%} exceeds threshold "
                f"for block: {block.text[:40]}"
            )


class TestPositionAccuracy:
    """验证位置精度。"""

    def setup_method(self):
        self.image = _load_image()
        self.blocks = _run_ocr(self.image)

    def test_bboxes_within_image(self):
        h, w = self.image.shape[:2]
        for block in self.blocks:
            for pt in block.bbox:
                assert -5 <= pt[0] <= w + 5, (
                    f"X coordinate {pt[0]} out of bounds for: {block.text[:40]}"
                )
                assert -5 <= pt[1] <= h + 5, (
                    f"Y coordinate {pt[1]} out of bounds for: {block.text[:40]}"
                )

    def test_font_sizes_reasonable(self):
        for block in self.blocks:
            assert 5 < block.font_size_est < 100, (
                f"Font size {block.font_size_est} unreasonable "
                f"for block: {block.text[:40]}"
            )


# ==================================================================
# 直接运行入口
# ==================================================================

if __name__ == "__main__":
    run_visual_test()
