from typing import Any

from langgraph.checkpoint.memory import InMemorySaver


def create_memory_checkpointer() -> InMemorySaver:
    """创建仅用于单进程学习环境的内存 checkpoint 存储。"""

    return InMemorySaver()


def thread_config(thread_id: str) -> dict[str, Any]:
    """构造 LangGraph checkpoint 所需的线程配置。"""

    normalized_thread_id = thread_id.strip()
    if not normalized_thread_id:
        raise ValueError("thread_id 不能为空")
    return {"configurable": {"thread_id": normalized_thread_id}}
