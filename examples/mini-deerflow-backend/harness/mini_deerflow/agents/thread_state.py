from typing import Annotated, TypedDict
import operator
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from langchain.agents import AgentState

class ThreadState(AgentState):
    model_calls: Annotated[int, operator.add]