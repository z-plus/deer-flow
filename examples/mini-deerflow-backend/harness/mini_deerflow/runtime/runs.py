from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from langchain_core.messages import HumanMessage
from mini_deerflow.streaming import MemoryStreamBridge

# 定义运行时类，调用方需要提供异步方法
class AgentRuntime(Protocol):
    # 运行Agent时需要的最小异步方法
    async def ainvoke(self,
        input: dict[str, Any],
        *,
        config: dict[str, Any],
        context: dict[str, str],) -> dict[str, Any]: ...

class RunStatus(StrEnum):
    """一次 Run 的生命周期状态。"""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class RunNotFoundError(RuntimeError):
    """请求的 Run 不存在时抛出。"""


@dataclass
class RunSnapshot:
    """可安全返回给调用方的快照"""
    run_id: str
    thread_id: str
    user_id: str
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    output: str | None = None
    error: str | None = None

class RunManager:
    """在单进程内管理异步 Agent Run。"""

    def __init__(self, agent: AgentRuntime, bridge: MemoryStreamBridge):
        self._agent = agent
        # 运行快照, key 运行时id，每个运行的唯一id， value是快照
        self._runs: dict[str, RunSnapshot] = {}
        # 异步任务，key是运行时 run_id, value 是异步运行的任务
        self._tasks: dict[str, asyncio.Task[None]] = {}
        # 异步任务锁
        self._lock = asyncio.Lock()
        # StreamBridge 只传递事件，不负责 Run 状态和 Agent 执行。
        self._bridge = bridge

    async def create_run(self,
                         *,
                         thread_id: str,
                         user_id: str,
                         message: str) -> RunSnapshot:
        """创建Run 并立刻返回快照"""

        # 用户消息不能为空
        if not message.strip():
            raise ValueError("message 不能为空")

        run_id = uuid4().hex
        now = datetime.now(UTC)
        # 快照信息，表示agent正在排队运行中
        snapshot = RunSnapshot(run_id=run_id, thread_id=thread_id, user_id=user_id, status=RunStatus.QUEUED,
            created_at=now,
            updated_at=now,)

        # 加锁
        async with self._lock:
            # 记录快造信息
            self._runs[run_id] = snapshot
            task = asyncio.create_task(
                self._execute(run_id=run_id, message=message),
                name=f"mini-deerflow-run-{run_id}",
            )
            self._tasks[run_id] = task
            # 任务完成后清理 asyncio task, runsnapshot 继续保留提供查询
            task.add_done_callback(lambda _: self._tasks.pop(run_id, None))
        # 深度拷贝对象，返回副本，防止路由或其他调用方直接修改 Manager 内部对象。
        return replace(snapshot)

    async def get_run(self, run_id: str) -> RunSnapshot:
        """读取 Run 的最新快照。"""

        async with self._lock:
            snapshot = self._runs.get(run_id)
            if snapshot is None:
                raise RunNotFoundError(f"Run 不存在: {run_id}")
            return replace(snapshot)

    async def aclose(self) -> None:
        """取消仍在执行的后台任务，用于应用关闭。"""

        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute(self, run_id: str, message: str) -> None:
        """在后台执行 Agent，并将成功或失败写回 Run 快照。"""

        # 开始执行任务，更新快照状态
        await self._update(run_id, status=RunStatus.RUNNING)
        snapshot = await self.get_run(run_id)
        try:
            thread_config = {"configurable": {"thread_id": snapshot.thread_id}}
            print(message)
            result = await self._agent.ainvoke(
                # create_agent() 的状态字段固定为 messages（复数）。
                input={"messages": [HumanMessage(content=message)]},
                config=thread_config,
                context={
                    "thread_id": snapshot.thread_id,
                    "user_id": snapshot.user_id,
                }
            )
            # create_agent() 返回完整的 State， HTTP 层只需要最后一条回答的文笔
            output = self._extract_output(result)
            await self._update(
                run_id,
                status=RunStatus.COMPLETED,
                output=output,
            )

        except asyncio.CancelledError:
            # 取消不是普通失败。保留该异常，让上层关闭或后续取消逻辑处理。
            raise
        except Exception as exc:
            # 教学版本把异常转换成可查询的 failed 状态，避免后台任务静默失败。
            await self._update(
                run_id,
                status=RunStatus.FAILED,
                error=str(exc) or type(exc).__name__,
            )

    async def _update(
        self,
        run_id: str,
        *,
        status: RunStatus,
        output: str | None = None,
        error: str | None = None,
    ) -> None:
        """在锁内原子更新 Run 的状态与结果。"""

        async with self._lock:
            snapshot = self._runs[run_id]
            snapshot.status = status
            snapshot.updated_at = datetime.now(UTC)
            snapshot.output = output
            snapshot.error = error

    @staticmethod
    def _extract_output(result: dict[str, Any]) -> str:
        """从 Agent State 的最后一条消息提取面向用户的回答。"""

        messages = result.get("messages", [])
        if not messages:
            return ""
        content = messages[-1].content
        return content if isinstance(content, str) else str(content)

    async def stream(self,
                         *,
                         thread_id: str,
                         user_id: str,
                         message: str):
