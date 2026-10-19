from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool


class ChatModel(Protocol):
    """第一阶段 Agent 所需的最小模型契约。"""

    def invoke(self, messages: list[BaseMessage]) -> AIMessage: ...


class UnknownToolError(LookupError):
    """模型请求未注册工具时抛出。"""


class AgentLoopLimitError(RuntimeError):
    """Agent 未能在限定步数内生成最终答案时抛出。"""


@dataclass(frozen=True)
class AgentResult:
    """最终答案及其生成过程的完整轨迹。"""

    output: str
    messages: tuple[BaseMessage, ...]
    steps: int


def run_agent(
    user_input: str,
    *,
    model: ChatModel,
    tools: Sequence[BaseTool],
    max_steps: int = 8,
) -> AgentResult:
    """运行一个最小的“模型 → 工具 → 模型”循环。

    每调用一次模型记为一步。工具执行结果会记录为 ToolMessage，
    使模型在下一步中能够读取该结果。
    """

    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")

    tools_by_name = {tool.name: tool for tool in tools}
    if len(tools_by_name) != len(tools):
        raise ValueError("tool names must be unique")

    # 真实的 LangChain 聊天模型需要在调用前绑定工具 Schema。
    # 小型测试替身只需实现 invoke()，从而保证测试可离线运行。
    bind_tools = getattr(model, "bind_tools", None)
    runnable_model: Any = bind_tools(list(tools)) if callable(bind_tools) else model

    messages: list[BaseMessage] = [HumanMessage(content=user_input)]
    for step in range(1, max_steps + 1):
        response = runnable_model.invoke(messages)
        if not isinstance(response, AIMessage):
            raise TypeError("model.invoke() must return an AIMessage")

        messages.append(response)
        if not response.tool_calls:
            output = (
                response.content
                if isinstance(response.content, str)
                else str(response.content)
            )
            return AgentResult(output=output, messages=tuple(messages), steps=step)

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool = tools_by_name.get(tool_name)
            if tool is None:
                raise UnknownToolError(f"Model requested unknown tool: {tool_name}")

            result = tool.invoke(tool_call["args"])
            messages.append(
                ToolMessage(
                    content=str(result),
                    name=tool_name,
                    tool_call_id=tool_call["id"],
                )
            )

    raise AgentLoopLimitError(f"Agent did not finish within {max_steps} model steps")
