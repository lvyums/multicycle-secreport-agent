"""渲染器注册 — 启动时注册 md/docx 渲染器到工厂"""

from capability.render.render_base import RendererFactory
from capability.render.md_renderer import MdRenderer
from capability.render.docx_renderer import DocxRenderer


def register_renderers():
    RendererFactory.register(MdRenderer)
    RendererFactory.register(DocxRenderer)


register_renderers()
