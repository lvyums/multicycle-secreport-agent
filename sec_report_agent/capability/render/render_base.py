"""渲染器抽象 — 模板渲染统一接口 + 工厂

V1.1 支持 md / docx 两种输出；后续扩展 pdf/html
"""

from abc import ABC, abstractmethod
from typing import Optional

from model.struct.structs import RenderData


class Renderer(ABC):
    """渲染器基类"""

    ext: str = ""  # md / docx

    @abstractmethod
    def render(self, data: RenderData) -> str:
        """渲染为文本内容（docx 返回文件路径，md 返回 markdown 文本）"""
        ...

    @abstractmethod
    def render_to_file(self, data: RenderData, file_path: str) -> str:
        """渲染并保存到指定文件，返回绝对路径"""
        ...


class RendererFactory:
    """渲染器工厂 — 按扩展名注册/获取"""

    _registry: dict[str, type[Renderer]] = {}

    @classmethod
    def register(cls, renderer_cls: type[Renderer]):
        cls._registry[renderer_cls.ext] = renderer_cls

    @classmethod
    def get(cls, ext: str) -> Optional[Renderer]:
        renderer_cls = cls._registry.get(ext.lower())
        if not renderer_cls:
            raise ValueError(f"未注册的渲染器: {ext}，可用: {list(cls._registry.keys())}")
        return renderer_cls()

    @classmethod
    def available_exts(cls) -> list[str]:
        return list(cls._registry.keys())
