from langchain_deepseek import ChatDeepSeek
from langchain_openai.chat_models.base import BaseChatOpenAI


def model_factory(model:str) -> BaseChatOpenAI:
    return ChatDeepSeek(model=model)