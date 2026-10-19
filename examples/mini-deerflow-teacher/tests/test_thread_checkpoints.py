import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from mini_deerflow.agents import build_agent_graph
from mini_deerflow.checkpoints import create_memory_checkpointer, thread_config
from mini_deerflow.tools import add


class ToolAwareFakeModel(FakeMessagesListChatModel):
    """支持绑定工具的 LangChain 离线聊天模型。"""

    def bind_tools(self, tools, **kwargs):
        return self


def request_context(thread_id: str) -> dict[str, str]:
    """构造与 thread 对应的业务上下文。"""

    return {"thread_id": thread_id, "user_id": "user-1"}


def test_same_thread_restores_previous_messages() -> None:
    model = ToolAwareFakeModel(
        responses=[
            AIMessage(content="我记住了，你喜欢红色。"),
            AIMessage(content="你喜欢红色。"),
        ]
    )
    agent = build_agent_graph(
        model=model,
        tools=[add],
        checkpointer=create_memory_checkpointer(),
    )
    config = thread_config("thread-a")

    agent.invoke(
        {"messages": [HumanMessage(content="我喜欢红色")]},
        config=config,
        context=request_context("thread-a"),
    )
    result = agent.invoke(
        {"messages": [HumanMessage(content="我喜欢什么颜色？")]},
        config=config,
        context=request_context("thread-a"),
    )

    assert [message.content for message in result["messages"]] == [
        "我喜欢红色",
        "我记住了，你喜欢红色。",
        "我喜欢什么颜色？",
        "你喜欢红色。",
    ]


def test_different_threads_keep_isolated_histories() -> None:
    model = ToolAwareFakeModel(
        responses=[
            AIMessage(content="线程 A 的回答"),
            AIMessage(content="线程 B 的回答"),
        ]
    )
    agent = build_agent_graph(
        model=model,
        tools=[add],
        checkpointer=create_memory_checkpointer(),
    )

    agent.invoke(
        {"messages": [HumanMessage(content="线程 A 的问题")]},
        config=thread_config("thread-a"),
        context=request_context("thread-a"),
    )
    agent.invoke(
        {"messages": [HumanMessage(content="线程 B 的问题")]},
        config=thread_config("thread-b"),
        context=request_context("thread-b"),
    )

    state_a = agent.get_state(thread_config("thread-a"))
    state_b = agent.get_state(thread_config("thread-b"))
    assert [message.content for message in state_a.values["messages"]] == [
        "线程 A 的问题",
        "线程 A 的回答",
    ]
    assert [message.content for message in state_b.values["messages"]] == [
        "线程 B 的问题",
        "线程 B 的回答",
    ]


def test_thread_id_must_not_be_empty() -> None:
    with pytest.raises(ValueError, match="thread_id 不能为空"):
        thread_config("   ")
