from typing import Sequence, TypedDict

from langchain.agents import create_agent
from langchain_core.tools import BaseTool

from mini_deerflow.agents.thread_state import ThreadState

class RequestContext(TypedDict):
    thread_id: str
    user_id: str


def make_lead_agent(model, tools: Sequence[BaseTool], checkpointer):
    """使用外部注入的模型、工具和检查点创建主 Agent。"""

    # 模型由 Gateway lifespan 创建并传入，这里不能再次创建或覆盖。
    return create_agent(
        model=model,
        tools=tools,
        system_prompt=("你是一个人工智能助手，帮助我完成任务"),
        context_schema=RequestContext,
        checkpointer=checkpointer,
        state_schema=ThreadState,
    )


