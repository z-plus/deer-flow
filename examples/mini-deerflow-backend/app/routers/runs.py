"""异步 Run 的 HTTP 适配层。

这里负责 HTTP 请求校验、状态码和响应序列化，不直接管理后台任务，也不
访问 RunManager 的内部字典。
"""
import json
from collections.abc import AsyncIterable
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Request, status
from mini_deerflow.runtime import (
    RunNotFoundError,
    RunSnapshot,
    RunStatus,
)
from mini_deerflow.streaming.base import END_SENTINEL, HEARTBEAT_SENTINEL, StreamGap
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from app.gateway.deps import get_run_manager

# 与 DeerFlow 相同：router 是模块级对象，由 Gateway 的 create_app() 统一挂载。
router = APIRouter(prefix="/api", tags=["runs"])



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
    error: str | None = None

    @classmethod
    def from_snapshot(cls, snapshot: RunSnapshot) -> "RunResponse":
        """把 Harness 数据类型转换成稳定的 HTTP 响应模型。"""

        return cls(**snapshot.__dict__)

@router.post("/threads/{thread_id}/runs",
            response_model=RunResponse,
            status_code=status.HTTP_202_ACCEPTED)
async def create_run(
        thread_id: str,
        body: CreateRunRequest,
        request: Request,
) -> RunResponse:
    """登记一次后台 Agent Run，并立即返回其状态。"""

    # 获取RunManager
    manager = get_run_manager(request)
    try:
        snapshot = await manager.create_run(
            thread_id=thread_id,
            user_id=body.user_id,
            message=body.message,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return RunResponse.from_snapshot(snapshot)

@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, request: Request) -> RunResponse:
    """查询 lifespan 中共享 RunManager 保存的 Run的状态。"""

    manager = get_run_manager(request)
    try:
        snapshot = await manager.get_run(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RunResponse.from_snapshot(snapshot)


def _encode_sse(event_id: str, event: str, data: object) -> str:
    """把内部事件编码为浏览器可识别的 SSE 文本帧。"""

    payload = json.dumps(data, ensure_ascii=False)
    return f"id: {event_id}\nevent: {event}\ndata: {payload}\n\n"

@router.post("/threads/{thread_id}/stream", response_model=None)
async def create_stream_run(
        thread_id: str,
        body: CreateRunRequest,
        request: Request) -> StreamingResponse:
    """流式输出 Run 事件，返回agent的完整推理过程"""

    # 获取RunManager
    manager = get_run_manager(request)
    try:
        snapshot = await manager.create_run(
            thread_id=thread_id,
            user_id=body.user_id,
            message=body.message,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    async def event_source() -> AsyncIterable:
        async for item in manager.stream(run_id=snapshot.run_id):
            if item is HEARTBEAT_SENTINEL:
                # SSE 注释不会触发业务事件，但能防止空闲连接被代理关闭。
                yield ": heartbeat\n\n"
            elif item is END_SENTINEL:
                yield _encode_sse("", "end", {})
            elif isinstance(item, StreamGap):
                yield _encode_sse(
                    "",
                    "gap",
                    {
                        "requested_event_id": item.requested_event_id,
                        "earliest_available_event_id": (
                            item.earliest_available_event_id
                        ),
                        "latest_available_event_id": (
                            item.latest_available_event_id
                        ),
                    },
                )
            else:
                yield _encode_sse(item.id, item.event, item.data)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Content-Location": f"api/runs/{snapshot.run_id}/stream"},
    )



@router.post("/runs/{run_id}/stream", response_model=None)
async def stream_run(run_id: str,
                     request: Request,
                     last_event_id: str | None = Header(default=None, alias="Last-Event-ID")) -> StreamingResponse:
    """流式输出 Run 事件，返回agent的完整推理过程"""

    manager = get_run_manager(request)
    if run_id:
        try:
            await manager.get_run(run_id)
        except RunNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def event_source() -> AsyncIterable:
        async for item in manager.stream(
            run_id=run_id,
        last_event_id=last_event_id,
        ):
            if item is HEARTBEAT_SENTINEL:
                # SSE 注释不会触发业务事件，但能防止空闲连接被代理关闭。
                yield ": heartbeat\n\n"
            elif item is END_SENTINEL:
                yield _encode_sse("", "end", {})
            elif isinstance(item, StreamGap):
                yield _encode_sse(
                    "",
                    "gap",
                    {
                        "requested_event_id": item.requested_event_id,
                        "earliest_available_event_id": (
                            item.earliest_available_event_id
                        ),
                        "latest_available_event_id": (
                            item.latest_available_event_id
                        ),
                    },
                )
            else:
                yield _encode_sse(item.id, item.event, item.data)
    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
