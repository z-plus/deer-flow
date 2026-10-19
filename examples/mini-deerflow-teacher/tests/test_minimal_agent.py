from collections import deque
from dataclasses import dataclass, field
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from mini_deerflow.agents import (
    AgentLoopLimitError,
    UnknownToolError,
    run_agent,
)
from mini_deerflow.tools import add


@dataclass
class ScriptedModel:
    responses: deque[AIMessage]
    requests: list[list[Any]] = field(default_factory=list)

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.requests.append(list(messages))
        return self.responses.popleft()


def test_agent_returns_a_direct_model_answer() -> None:
    model = ScriptedModel(deque([AIMessage(content="你好，我是教学 Agent。")]))

    result = run_agent("你好", model=model, tools=[add])

    assert result.output == "你好，我是教学 Agent。"
    assert isinstance(result.messages[0], HumanMessage)
    assert result.steps == 1


def test_agent_executes_a_tool_and_returns_the_follow_up_answer() -> None:
    model = ScriptedModel(
        deque(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "add", "args": {"a": 2, "b": 3}, "id": "call-1"}
                    ],
                ),
                AIMessage(content="2 + 3 = 5"),
            ]
        )
    )

    result = run_agent("计算 2 + 3", model=model, tools=[add])

    assert result.output == "2 + 3 = 5"
    assert result.steps == 2
    tool_message = next(
        message for message in result.messages if isinstance(message, ToolMessage)
    )
    assert tool_message.content == "5"
    assert tool_message.tool_call_id == "call-1"
    assert len(model.requests) == 2


def test_agent_rejects_an_unknown_tool() -> None:
    model = ScriptedModel(
        deque(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "delete_everything", "args": {}, "id": "call-2"}
                    ],
                )
            ]
        )
    )

    with pytest.raises(UnknownToolError, match="delete_everything"):
        run_agent("调用不存在的工具", model=model, tools=[add])


def test_agent_stops_at_the_step_limit() -> None:
    model = ScriptedModel(
        deque(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "add", "args": {"a": 1, "b": 1}, "id": "call-3"}
                    ],
                )
            ]
        )
    )

    with pytest.raises(AgentLoopLimitError, match="1"):
        run_agent("一直调用工具", model=model, tools=[add], max_steps=1)


def test_add_tool_has_a_schema_and_computes_the_sum() -> None:
    assert add.name == "add"
    assert add.invoke({"a": 4, "b": 7}) == 11
    assert set(add.args) == {"a", "b"}
