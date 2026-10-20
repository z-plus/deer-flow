from langchain_core.language_models import BaseChatModel
from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI

from mini_deerflow.models.provider_custom import ProviderCustom
from mini_deerflow.models.provider_deepseek import ProviderDeepSeek


def create_chat_model(model: str | None = None, provider: str = "openai", *, app_config: dict | None = None, **kwargs) -> BaseChatModel:
    """Create a chat model from the config file.
    Args:
    """
    model_provider = None
    # if provider == "openai":
    #     model_provider = ChatOpenAI(model=name,)

    if provider == "deepseek":
        model_provider = ProviderDeepSeek.model_factory(model=model)
    if model_provider is None:
        model_provider = ProviderCustom.model_factory(model=model)
    return model_provider