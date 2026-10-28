from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk

_REASONING_KEYS = ("reasoning_content", "reasoning", "thinking")
_REASONING_BLOCK_TYPES = {"reasoning", "thinking"}


def _reasoning(message: AIMessage | AIMessageChunk) -> Any:
    for key in _REASONING_KEYS:
        value = message.additional_kwargs.get(key)
        if value is not None:
            return value
    if isinstance(message.content, list):
        blocks = [block for block in message.content if isinstance(block, dict) and block.get("type") in _REASONING_BLOCK_TYPES]
        if blocks:
            return blocks
    return None


def message_chunk_to_stream_payload(message: AIMessage | AIMessageChunk) -> dict[str, Any]:
    """Convert one LangChain AI message into the mini stream contract."""
    payload: dict[str, Any] = {}
    if message.content:
        payload["content"] = message.content
    if (reasoning := _reasoning(message)) is not None:
        payload["reasoning_content"] = reasoning
    if isinstance(message, AIMessageChunk) and message.tool_call_chunks:
        payload["tool_call_chunks"] = message.tool_call_chunks
    elif message.tool_calls:
        payload["tool_calls"] = message.tool_calls
    return payload
