from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import openai
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI

_REASONING_FIELDS = ("reasoning", "reasoning_content", "thinking")


def _extract_reasoning(payload: Mapping[str, Any]) -> Any:
    for field in _REASONING_FIELDS:
        value = payload.get(field)
        if value is not None:
            return value
    return None


def _with_reasoning(message: AIMessage | AIMessageChunk, reasoning: Any) -> AIMessage | AIMessageChunk:
    additional_kwargs = dict(message.additional_kwargs)
    additional_kwargs["reasoning_content"] = reasoning
    return message.model_copy(update={"additional_kwargs": additional_kwargs})


class CustomOpenAIChatModel(ChatOpenAI):
    """OpenAI-compatible client that preserves common provider reasoning fields."""

    def _create_chat_result(
        self,
        response: dict | openai.BaseModel,
        generation_info: dict | None = None,
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info=generation_info)
        payload = response if isinstance(response, dict) else response.model_dump()
        for generation, choice in zip(result.generations, payload.get("choices", [])):
            if not isinstance(generation, ChatGeneration) or not isinstance(generation.message, AIMessage):
                continue
            reasoning = _extract_reasoning(choice.get("message") or {})
            if reasoning is not None:
                generation.message = _with_reasoning(generation.message, reasoning)
        return result

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        generation = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
        if generation is None or not isinstance(generation.message, AIMessageChunk):
            return generation
        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices") or []
        reasoning = _extract_reasoning(choices[0].get("delta") or {}) if choices else None
        if reasoning is not None:
            generation.message = _with_reasoning(generation.message, reasoning)
        return generation


class ProviderCustom:
    @staticmethod
    def model_factory(model: str, **kwargs: Any) -> BaseChatModel:
        return CustomOpenAIChatModel(model=model, **kwargs)
