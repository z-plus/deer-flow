from typing import Sequence, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver

from mini_deerflow.models.factory import create_chat_model
from mini_deerflow.tools import arithmetic
from mini_deerflow.agents.lead_agent.agent import _make_lead_agent

def test_agent_returns_a_direct_model_answer() -> None:
    config = {"configurable": {"thread_id": "1"}}
    context: RequestContext = {"thread_id": "1", "user_id": "2"}

    for part in _make_lead_agent(config={}, tools=[arithmetic.add, arithmetic.multiply]).stream(
            input={"messages": [HumanMessage(content="1 * 1等于几")]}, context=context, config=config,
            stream_mode=["messages", "values"], version="v2"):
        print(part)
