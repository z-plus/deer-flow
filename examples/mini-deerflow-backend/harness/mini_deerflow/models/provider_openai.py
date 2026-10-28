from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI


class ProviderOpenAI:
    @staticmethod
    def model_factory(model: str, **kwargs: Any) -> BaseChatModel:
        return ChatOpenAI(model=model, **kwargs)
