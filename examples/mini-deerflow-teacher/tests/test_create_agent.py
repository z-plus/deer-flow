from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import Field

from mini_deerflow.agents import ThreadState, build_agent_graph
from mini_deerflow.tools import add


class ToolAwareFakeModel(FakeMessagesListChatModel):
    """支持绑定工具的 LangChain 离线聊天模型。"""

    bound_tool_names: list[str] = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        self.bound_tool_names = [tool.name for tool in tools]
        return self


def test_create_agent_preserves_the_complete_tool_call_history() -> None:
    model = ToolAwareFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "add",
                        "args": {"a": 7, "b": 5},
                        "id": "call-add",
                    }
                ],
            ),
            AIMessage(content="7 + 5 = 12"),
        ]
    )
    agent = build_agent_graph(model=model, tools=[add])

    result: ThreadState = agent.invoke(
        {"messages": [HumanMessage(content="计算 7 + 5")]},
        context={"thread_id": "thread-1", "user_id": "user-1"},
    )

    assert model.bound_tool_names == ["add"]
    assert [type(message) for message in result["messages"]] == [
        HumanMessage,
        AIMessage,
        ToolMessage,
        AIMessage,
    ]
    assert result["messages"][2].content == "12"
    assert result["messages"][-1].content == "7 + 5 = 12"


def test_create_agent_returns_a_direct_answer() -> None:
    model = ToolAwareFakeModel(responses=[AIMessage(content="直接回答")])
    agent = build_agent_graph(model=model, tools=[add])

    result: ThreadState = agent.invoke(
        {"messages": [HumanMessage(content="你好")]},
        context={"thread_id": "thread-2", "user_id": "user-1"},
    )

    assert [message.content for message in result["messages"]] == [
        "你好",
        "直接回答",
    ]
