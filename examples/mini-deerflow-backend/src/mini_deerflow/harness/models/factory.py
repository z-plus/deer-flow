from langchain_core.language_models import BaseChatModel
from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI


def create_chat_model(name: str | None = None, provider: str = "openai", *, app_config: dict | None = None, **kwargs) -> BaseChatModel:
    """Create a chat model from the config file.
    Args:
    """

    if provider == "openai":
        model_provider = ChatOpenAI(model=name,)
    elif provider == "deepseek":
        model_provider = ChatDeepSeek(model=name,)
    else:
        raise ValueError(f"Unknown provider {provider}")
    return model_provider