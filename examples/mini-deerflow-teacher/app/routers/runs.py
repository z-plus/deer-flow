"""异步 Run 的 HTTP 适配层。

这里负责 HTTP 请求校验、状态码和响应序列化，不直接管理后台任务，也不
访问 RunManager 的内部字典。
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from mini_deerflow.runtime import (
    RunManager,
    RunNotFoundError,
    RunSnapshot,
    RunStatus,
)


class CreateRunRequest(BaseModel):
    """创建异步 Run 的请求。

    Pydantic 在进入路由函数前完成基本校验，因此空字符串 user_id 会直接
    得到 422；纯空格 message 则由 RunManager 的业务校验处理。
    """

    message: str = Field(min_length=1)
    user_id: str = Field(default="local-user", min_length=1)


class RunResponse(BaseModel):
    """HTTP 层公开的 Run 信息。"""

    run_id: str
    thread_id: str
    user_id: str
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    output: str | None = None
    error: str | None = None

    @classmethod
    def from_snapshot(cls, snapshot: RunSnapshot) -> "RunResponse":
        """把 Harness 数据类型转换成稳定的 HTTP 响应模型。"""

        return cls(**snapshot.__dict__)


def create_runs_router(manager: RunManager) -> APIRouter:
    """创建只依赖 RunManager 公共方法的 Run 路由。

    使用工厂函数传入 manager，既避免模块级全局单例，也方便测试时注入
    假 Agent 对应的 RunManager。
    """

    router = APIRouter(prefix="/api")

    @router.post(
        "/threads/{thread_id}/runs",
        response_model=RunResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_run(thread_id: str, body: CreateRunRequest) -> RunResponse:
        # 此处只等待“登记 Run”，不会等待模型完成，所以接口返回 HTTP 202。
        try:
            snapshot = await manager.create_run(
                thread_id=thread_id,
                user_id=body.user_id,
                message=body.message,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return RunResponse.from_snapshot(snapshot)

    @router.get("/runs/{run_id}", response_model=RunResponse)
    async def get_run(run_id: str) -> RunResponse:
        # 查询接口没有触发 Agent，仅读取 Manager 保存的最新快照。
        try:
            snapshot = await manager.get_run(run_id)
        except RunNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return RunResponse.from_snapshot(snapshot)

    return router
