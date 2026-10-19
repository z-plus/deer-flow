from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI


def create_chat_model(
    name: str | None = None,
    provider: str = "openai",
    **kwargs: Any,
) -> BaseChatModel:
    """创建聊天模型，但不调用模型，也不主动读取凭据。"""

    if provider == "openai":
        return ChatOpenAI(model=name, **kwargs)
    if provider == "deepseek":
        return ChatDeepSeek(model=name, **kwargs)
    raise ValueError(f"Unknown provider: {provider}")
