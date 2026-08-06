"""渲染器测试 — md/docx 双格式输出"""
import sys, os, tempfile
sys.path.insert(0, ".")

import pytest

from capability.render.md_renderer import MdRenderer
from capability.render.docx_renderer import DocxRenderer
from capability.render.render_base import RendererFactory
from model.struct.structs import RenderData


def _data():
    return RenderData(
        cycle="MONTHLY", cycle_label="月报",
        window_start="2026-07-01 00:00:00", window_end="2026-08-01 00:00:00",
        generated_at="2026-08-06 12:00:00",
        metric={"alert": {"total": 10}, "vuln": {"total": 2}},
        judge={
            "risk_level": "HIGH",
            "sections": {
                "overview": "总体态势良好", "alert": "告警 10 起",
                "vuln": "漏洞 2 条", "attack": "TOP 源 1.1.1.1",
                "trend": "趋势平稳", "advice": "加强防护",
            },
        },
        extra={"title": "测试报告"},
    )


def test_md_render():
    md = MdRenderer().render(_data())
    assert "# 测试报告" in md
    assert "月报" in md
    assert "HIGH" in md
    assert "总体态势良好" in md


def test_md_render_to_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "out.md")
        MdRenderer().render_to_file(_data(), path)
        assert os.path.exists(path)
        assert os.path.getsize(path) > 100


def test_docx_render_to_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "out.docx")
        DocxRenderer().render_to_file(_data(), path)
        assert os.path.exists(path)
        assert os.path.getsize(path) > 1000


def test_factory_registry():
    RendererFactory.register(MdRenderer)
    r = RendererFactory.get("md")
    assert isinstance(r, MdRenderer)
    with pytest.raises(ValueError):
        RendererFactory.get("unknown")
