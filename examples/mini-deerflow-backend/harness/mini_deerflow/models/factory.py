from typing import Any

from langchain_core.language_models import BaseChatModel

from mini_deerflow.models.provider_custom import ProviderCustom
from mini_deerflow.models.provider_deepseek import ProviderDeepSeek
from mini_deerflow.models.provider_openai import ProviderOpenAI

_PROVIDERS = {
    "openai": ProviderOpenAI,
    "deepseek": ProviderDeepSeek,
    "custom": ProviderCustom,
}


def create_chat_model(
    model: str,
    provider: str = "openai",
    *,
    app_config: dict[str, Any] | None = None,
    **kwargs: Any,
) -> BaseChatModel:
    """Create an OpenAI, DeepSeek, or custom OpenAI-compatible chat model."""
    try:
        model_provider = _PROVIDERS[provider.lower()]
    except KeyError as exc:
        supported = ", ".join(_PROVIDERS)
        raise ValueError(f"Unsupported model provider {provider!r}; expected one of: {supported}") from exc

    config = {**(app_config or {}), **kwargs}
    return model_provider.model_factory(model=model, **config)
