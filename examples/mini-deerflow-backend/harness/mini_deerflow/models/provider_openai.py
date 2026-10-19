from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_openai.chat_models.base import BaseChatOpenAI


def model_factory(model:str) -> BaseChatModel:
    return ChatOpenAI(model=model)