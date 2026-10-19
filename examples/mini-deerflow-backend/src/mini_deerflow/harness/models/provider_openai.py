from langchain_openai import ChatOpenAI
from langchain_openai.chat_models.base import BaseChatOpenAI


def model_factory(model:str) -> BaseChatOpenAI:
    return ChatOpenAI(model=model)