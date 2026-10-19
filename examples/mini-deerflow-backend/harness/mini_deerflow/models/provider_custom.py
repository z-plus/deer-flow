import os

from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel

load_dotenv(override=True)
from langchain.chat_models import init_chat_model

class ProviderCustom:

    @staticmethod
    def model_factory(model:str) -> BaseChatModel:
        return init_chat_model(model=model,
                               model_provider="openai",
                               base_url="https://api.openai-proxy.org/v1",
                               api_key=os.environ["OPENAI_API_KEY"])