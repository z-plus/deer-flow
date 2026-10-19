from typing import Sequence, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver

from mini_deerflow.models.factory import create_chat_model
from mini_deerflow.tools import arithmetic
from mini_deerflow.agents.thread_state import ThreadState

class RequestContext(TypedDict):
    thread_id: str
    user_id: str


def _make_lead_agent(config: dict, tools: Sequence[BaseTool]):
    """
    创建智能体
    """

    # TODO init model
    model = create_chat_model(name="gpt-5.6-sol", provider="")
    return create_agent(
        model=model,
        tools=tools,
        system_prompt=("你是一个人工智能助手，帮助我完成任务"),
        context_schema=RequestContext,
        checkpointer=InMemorySaver(),
        state_schema=ThreadState,
    )


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "1"}}
    context: RequestContext = {"thread_id": "1", "user_id": "2"}

    for part in _make_lead_agent(config={}, tools=[arithmetic.add, arithmetic.multiply]).stream(
            input={"messages": [HumanMessage(content="1 * 1等于几")]}, context=context, config=config,
            stream_mode=["messages", "values"], version="v2"):
        print(part)
