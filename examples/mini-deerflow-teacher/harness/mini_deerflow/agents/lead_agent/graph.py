from typing import Sequence, TypedDict

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver

from mini_deerflow.agents.thread_state import ThreadState


SYSTEM_PROMPT = "你是一个人工智能助手，帮助用户准确地完成任务。"


class RequestContext(TypedDict):
    """一次 Agent 请求携带的业务上下文。"""

    thread_id: str
    user_id: str


def build_agent_graph(
    *,
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    checkpointer: BaseCheckpointSaver | None = None,
):
    """使用 LangChain ``create_agent`` 创建 Agent 图。"""

    return create_agent(
        model=model,
        tools=list(tools),
        system_prompt=SYSTEM_PROMPT,
        state_schema=ThreadState,
        context_schema=RequestContext,
        checkpointer=checkpointer,
    )
