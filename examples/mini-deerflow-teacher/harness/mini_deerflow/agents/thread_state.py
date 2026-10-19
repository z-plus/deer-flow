"""在 LangChain AgentState 基础上扩展教学状态。"""

import operator
from typing import Annotated

from langchain.agents import AgentState


class ThreadState(AgentState):
    """Agent thread 的状态结构。

    ``messages`` 及其 reducer 直接继承自 LangChain 的 ``AgentState``；
    ``model_calls`` 演示如何增加一个使用加法 reducer 的自定义字段。
    """

    model_calls: Annotated[int, operator.add]
