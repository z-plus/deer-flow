from langchain_core.language_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek


class ProviderDeepSeek:

    @staticmethod
    def model_factory(model:str) -> BaseChatModel:
        return ChatDeepSeek(model=model)