import asyncio

from langchain_core.messages import AIMessage, AIMessageChunk
from mini_deerflow.runtime import RunManager
from mini_deerflow.runtime.message_stream import message_chunk_to_stream_payload
from mini_deerflow.streaming import MemoryStreamBridge


class ReasoningAgent:
    async def astream(self, *args, **kwargs):
        yield AIMessageChunk(
            content=[{"type": "reasoning", "reasoning": "thinking"}],
            tool_call_chunks=[{"name": "add", "args": '{"a":', "id": "call-1", "index": 0}],
        ), {}
        yield AIMessageChunk(content=[{"type": "text", "text": "answer"}]), {}


def test_run_manager_streams_normalized_reasoning() -> None:
    async def run():
        manager = RunManager(ReasoningAgent(), bridge=MemoryStreamBridge())
        snapshot = await manager.create_run(thread_id="thread", user_id="user", message="question")
        await asyncio.gather(*manager._tasks.values())
        events = [item.data async for item in manager.stream(snapshot.run_id) if hasattr(item, "data")]
        return await manager.get_run(snapshot.run_id), events

    snapshot, events = asyncio.run(run())

    assert any(event.get("reasoning_content") == [{"type": "reasoning", "reasoning": "thinking"}] for event in events)
    assert any(event.get("tool_call_chunks") for event in events)
    assert any(event.get("content") == [{"type": "text", "text": "answer"}] for event in events)
    assert {"status": "completed"} in events
    assert not hasattr(snapshot, "output")


def test_message_chunk_converter_keeps_content_reasoning_and_tool_calls() -> None:
    message = AIMessage(
        content=[{"type": "text", "text": "answer"}],
        additional_kwargs={"reasoning": "thinking"},
        tool_calls=[{"name": "add", "args": {"a": 1, "b": 2}, "id": "call-1", "type": "tool_call"}],
    )

    payload = message_chunk_to_stream_payload(message)

    assert payload == {
        "content": [{"type": "text", "text": "answer"}],
        "reasoning_content": "thinking",
        "tool_calls": [{"name": "add", "args": {"a": 1, "b": 2}, "id": "call-1", "type": "tool_call"}],
    }
