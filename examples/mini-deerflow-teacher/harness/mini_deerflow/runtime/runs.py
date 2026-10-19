"""异步 Run 的核心生命周期管理。

这个模块属于 Harness，不依赖 FastAPI。它只关心如何登记一次 Agent 执行、
如何在后台运行它，以及如何向调用方提供可查询的状态快照。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from langchain_core.messages import HumanMessage

from mini_deerflow.checkpoints import thread_config


class AgentRuntime(Protocol):
    """RunManager 调用 Agent 所需的最小异步接口。

    Protocol 使用“结构化类型”：真实 Agent 不需要继承这个类，只要提供
    相同签名的 ``ainvoke`` 方法，就可以交给 RunManager 使用。
    """

    async def ainvoke(
        self,
        input: dict[str, Any],
        *,
        config: dict[str, Any],
        context: dict[str, str],
    ) -> dict[str, Any]: ...


class RunStatus(StrEnum):
    """一次 Run 的生命周期状态。"""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunNotFoundError(LookupError):
    """请求的 Run 不存在时抛出。"""


@dataclass
class RunSnapshot:
    """可安全返回给调用方的 Run 状态快照。

    output 只在成功时有值，error 只在失败时有值。时间统一使用 UTC，
    避免服务运行在不同时区时产生歧义。
    """

    run_id: str
    thread_id: str
    user_id: str
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    output: str | None = None
    error: str | None = None


class RunManager:
    """在单进程内管理异步 Agent Run。

    ``_runs`` 保存可查询的业务状态，``_tasks`` 保存正在执行的 asyncio
    任务。两者职责不同：任务结束后可以从 _tasks 移除，但 Run 快照仍需
    保留，供客户端继续查询结果。
    """

    def __init__(self, agent: AgentRuntime):
        # 依赖注入：Manager 只依赖 ainvoke 契约，不负责创建具体模型或 Agent。
        self._agent = agent
        # 教学阶段使用内存字典；后续持久化阶段会替换为数据库仓库。
        self._runs: dict[str, RunSnapshot] = {}
        # 保留强引用，避免后台任务在完成前丢失，也方便应用关闭时统一取消。
        self._tasks: dict[str, asyncio.Task[None]] = {}
        # HTTP 请求和后台任务可能同时读写字典，因此所有共享状态都经过锁。
        self._lock = asyncio.Lock()

    async def create_run(
        self,
        *,
        thread_id: str,
        user_id: str,
        message: str,
    ) -> RunSnapshot:
        """创建 Run 并立即返回 queued 快照。"""

        if not message.strip():
            raise ValueError("message 不能为空")

        # run_id 标识“一次执行”；它与表示“对话历史”的 thread_id 不同。
        run_id = uuid4().hex
        now = datetime.now(UTC)
        snapshot = RunSnapshot(
            run_id=run_id,
            thread_id=thread_id,
            user_id=user_id,
            status=RunStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )
        async with self._lock:
            # 必须先登记 queued 快照，再启动后台任务。这样后台任务无论多快
            # 开始，都能找到对应 Run 并把它更新为 running。
            self._runs[run_id] = snapshot
            task = asyncio.create_task(
                self._execute(run_id=run_id, message=message),
                name=f"mini-deerflow-run-{run_id}",
            )
            self._tasks[run_id] = task
            # 任务完成后只清理 asyncio Task；RunSnapshot 继续保留供查询。
            task.add_done_callback(lambda _: self._tasks.pop(run_id, None))
        # 返回副本，防止路由或其他调用方直接修改 Manager 内部对象。
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

    async def _execute(self, *, run_id: str, message: str) -> None:
        """在后台执行 Agent，并将成功或失败写回 Run 快照。"""

        # 后台任务真正获得执行机会后，Run 才从 queued 进入 running。
        await self._update(run_id, status=RunStatus.RUNNING)
        snapshot = await self.get_run(run_id)
        try:
            # thread_id 同时进入 checkpoint 配置和业务 Context：前者用于恢复
            # 对话状态，后者供 Agent/中间件读取本次请求所属的用户与 thread。
            result = await self._agent.ainvoke(
                {"messages": [HumanMessage(content=message)]},
                config=thread_config(snapshot.thread_id),
                context={
                    "thread_id": snapshot.thread_id,
                    "user_id": snapshot.user_id,
                },
            )
            # create_agent() 返回完整 State；HTTP 层只需要最后一条回答文本。
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
