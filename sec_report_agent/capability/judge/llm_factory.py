"""大模型工厂 — 统一创建 LLM 客户端实例"""

from abc import ABC, abstractmethod
from typing import Optional
import time

from openai import AsyncOpenAI

from common.logger import LogManager

logger = LogManager.get_logger()


class BaseLLMClient(ABC):
    """LLM 客户端基类"""

    def __init__(self, api_key: str, base_url: str, model_name: str, temperature: float = 0.1, timeout: int = 10):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.temperature = temperature
        self.timeout = timeout
        self.client: Optional[AsyncOpenAI] = None

    @abstractmethod
    async def chat(self, messages: list[dict], temperature: Optional[float] = None, timeout: Optional[int] = None) -> dict:
        """调用大模型，返回 {content, success, error}"""
        ...

    @abstractmethod
    async def chat_stream(self, messages: list[dict], temperature: Optional[float] = None, timeout: Optional[int] = None):
        """流式调用大模型，逐个 yield token

        Yields:
            str: 每个 token 的文本片段
        """
        ...
        yield ""  # (workaround: abstract generator)

    async def close(self):
        """关闭客户端会话"""
        if self.client:
            await self.client.close()


class DeepSeekClient(BaseLLMClient):
    """DeepSeek API 实现"""

    async def chat(self, messages: list[dict], temperature: Optional[float] = None, timeout: Optional[int] = None) -> dict:
        temp = temperature if temperature is not None else self.temperature
        t = timeout if timeout is not None else self.timeout
        start = time.monotonic()
        success = True
        try:
            self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url, timeout=t)
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temp,
            )
            content = response.choices[0].message.content or ""
            return {"content": content, "success": True, "error": None}
        except Exception as e:
            success = False
            logger.error(f"LLM 调用失败: {e}")
            return {"content": None, "success": False, "error": str(e)}
        finally:
            logger.info(f"[LLM] DeepSeekClient 调用 {'成功' if success else '失败'} {(time.monotonic() - start) * 1000:.0f}ms")

    async def chat_stream(self, messages: list[dict], temperature: Optional[float] = None, timeout: Optional[int] = None):
        """流式调用 DeepSeek，逐个 yield token"""
        temp = temperature if temperature is not None else self.temperature
        t = timeout if timeout is not None else self.timeout or 60  # 流式需要更长超时
        try:
            self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url, timeout=t)
            stream = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temp,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            logger.error(f"LLM 流式调用失败: {e}")
            yield f"\n\n[错误] LLM 流式响应失败: {str(e)}"


class LightweightClient(BaseLLMClient):
    """轻量模型实现（Qwen/Distill）"""

    async def chat(self, messages: list[dict], temperature: Optional[float] = None, timeout: Optional[int] = None) -> dict:
        temp = temperature if temperature is not None else self.temperature
        t = timeout if timeout is not None else self.timeout
        start = time.monotonic()
        success = True
        try:
            self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url, timeout=t)
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temp,
                max_tokens=512,
            )
            content = response.choices[0].message.content or ""
            return {"content": content, "success": True, "error": None}
        except Exception as e:
            success = False
            logger.error(f"轻量 LLM 调用失败: {e}")
            return {"content": None, "success": False, "error": str(e)}
        finally:
            logger.info(f"[LLM] 轻量模型调用 {'成功' if success else '失败'} {(time.monotonic() - start) * 1000:.0f}ms")

    async def chat_stream(self, messages: list[dict], temperature: Optional[float] = None, timeout: Optional[int] = None):
        """轻量模型流式调用"""
        temp = temperature if temperature is not None else self.temperature
        t = timeout if timeout is not None else self.timeout or 60
        try:
            self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url, timeout=t)
            stream = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temp,
                max_tokens=512,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            logger.error(f"轻量 LLM 流式调用失败: {e}")
            yield f"\n\n[错误] 流式响应失败: {str(e)}"


class LLMFactory:
    """大模型工厂 — 统一创建和管理 LLM 客户端（注册模式）"""

    _registry: dict[str, type[BaseLLMClient]] = {}
    _instances: dict[str, BaseLLMClient] = {}

    @classmethod
    def register(cls, model_type: str, client_class: type[BaseLLMClient]):
        """注册 LLM 客户端类"""
        cls._registry[model_type] = client_class
        logger.info(f"注册 LLM 客户端: {model_type} -> {client_class.__name__}")

    @classmethod
    def create(cls, model_type: str = "main") -> BaseLLMClient:
        """根据配置返回对应 LLM 实例"""
        from config.settings import settings

        client_class = cls._registry.get(model_type)
        if not client_class:
            raise ValueError(f"未知模型类型: {model_type}，已注册: {list(cls._registry.keys())}")

        if model_type == "main":
            return client_class(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                model_name=settings.llm_model_name,
                temperature=settings.llm_temperature,
                timeout=settings.llm_timeout,
            )
        elif model_type == "light":
            return client_class(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                model_name=settings.llm_light_model_name,
                temperature=settings.llm_temperature,
                timeout=settings.llm_timeout,
            )
        return client_class(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model_name=settings.llm_model_name,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout,
        )

    @classmethod
    async def get_main_llm(cls) -> BaseLLMClient:
        """获取主力模型（单例）"""
        if "main" not in cls._instances:
            cls._instances["main"] = cls.create("main")
        return cls._instances["main"]

    @classmethod
    async def get_light_llm(cls) -> BaseLLMClient:
        """获取轻量模型（单例）"""
        if "light" not in cls._instances:
            cls._instances["light"] = cls.create("light")
        return cls._instances["light"]

    @classmethod
    async def close_all(cls):
        """关闭所有 LLM 客户端"""
        for instance in cls._instances.values():
            await instance.close()
        cls._instances.clear()


# ── 默认注册 ──
LLMFactory.register("main", DeepSeekClient)
LLMFactory.register("light", LightweightClient)