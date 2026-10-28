from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from mini_deerflow.models import factory
from mini_deerflow.models.provider_custom import CustomOpenAIChatModel, _extract_reasoning


@pytest.mark.parametrize("provider", ["openai", "deepseek", "custom"])
def test_factory_selects_provider_and_forwards_config(monkeypatch, provider: str) -> None:
    expected = Mock()
    model_factory = Mock(return_value=expected)
    monkeypatch.setattr(factory._PROVIDERS[provider], "model_factory", model_factory)

    actual = factory.create_chat_model(
        "model-name",
        provider,
        app_config={"temperature": 0.2, "timeout": 10},
        timeout=20,
    )

    assert actual is expected
    model_factory.assert_called_once_with(model="model-name", temperature=0.2, timeout=20)


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported model provider"):
        factory.create_chat_model("model-name", "unknown")


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"reasoning_content": "legacy"}, "legacy"),
        ({"reasoning": "reasoning"}, "reasoning"),
        ({"thinking": "thinking"}, "thinking"),
        ({"reasoning_content": "legacy", "reasoning": "canonical"}, "canonical"),
        ({}, None),
    ],
)
def test_custom_provider_accepts_common_reasoning_fields(payload, expected) -> None:
    assert _extract_reasoning(payload) == expected


def test_custom_provider_preserves_streamed_thinking(monkeypatch) -> None:
    generation = ChatGenerationChunk(message=AIMessageChunk(content="answer"))
    monkeypatch.setattr("langchain_openai.ChatOpenAI._convert_chunk_to_generation_chunk", Mock(return_value=generation))
    model = CustomOpenAIChatModel(model="custom", api_key="test", base_url="https://example.test/v1")

    actual = model._convert_chunk_to_generation_chunk(
        {"choices": [{"delta": {"thinking": "thought"}}]},
        AIMessageChunk,
        None,
    )

    assert actual.message.additional_kwargs["reasoning_content"] == "thought"


def test_custom_provider_preserves_non_streamed_reasoning(monkeypatch) -> None:
    result = ChatResult(generations=[ChatGeneration(message=AIMessage(content="answer"))])
    monkeypatch.setattr("langchain_openai.ChatOpenAI._create_chat_result", Mock(return_value=result))
    model = CustomOpenAIChatModel(model="custom", api_key="test", base_url="https://example.test/v1")

    actual = model._create_chat_result(
        {"choices": [{"message": {"reasoning": "thought", "content": "answer"}}]}
    )

    assert actual.generations[0].message.additional_kwargs["reasoning_content"] == "thought"
