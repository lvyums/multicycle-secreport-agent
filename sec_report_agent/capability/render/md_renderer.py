"""Markdown 渲染器 — Jinja2 模板渲染月报"""

import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config.settings import settings
from capability.render.render_base import Renderer
from model.struct.structs import RenderData
from common.logger.logger import LogManager

logger = LogManager.get_logger()

_env = Environment(
    loader=FileSystemLoader(settings.template_root),
    autoescape=select_autoescape(("html", "xml")),
    trim_blocks=True,
    lstrip_blocks=True,
)


class MdRenderer(Renderer):
    """Markdown 渲染器"""

    ext = "md"

    def render(self, data: RenderData) -> str:
        template = _env.get_template("monthly_report.md.j2")
        context = self._build_context(data)
        return template.render(**context)

    def render_to_file(self, data: RenderData, file_path: str) -> str:
        content = self.render(data)
        abs_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"[RENDER] MD 已保存: {abs_path} ({len(content)} 字符)")
        return abs_path

    @staticmethod
    def _build_context(data: RenderData) -> dict:
        judge = data.judge or {}
        sections = judge.get("sections") or {}
        metric = data.metric or {}
        alert = metric.get("alert") or {}
        return {
            "title": data.extra.get("title", f"{data.cycle_label}网络安全态势报告"),
            "cycle_label": data.cycle_label,
            "window_start": data.window_start,
            "window_end": data.window_end,
            "generated_at": data.generated_at,
            "risk_level": judge.get("risk_level", "LOW"),
            "sections": sections,
            "metric": {"alert": alert},
        }
