import asyncio

import httpx
import pytest
from langchain_core.messages import AIMessage

from app.gateway import create_app
from mini_deerflow.runtime import RunManager


@pytest.fixture
def anyio_backend():
    return "asyncio"


class SuccessfulAgent:
    """立即返回固定回答的异步 Agent。"""

    async def ainvoke(self, input, *, config, context):
        await asyncio.sleep(0)
        return {
            "messages": [
                *input["messages"],
                AIMessage(content=f"收到：{input['messages'][-1].content}"),
            ]
        }


class FailingAgent:
    """用于验证失败状态的异步 Agent。"""

    async def ainvoke(self, input, *, config, context):
        raise RuntimeError("模型暂时不可用")


async def wait_for_terminal_run(client: httpx.AsyncClient, run_id: str) -> dict:
    """轮询测试接口，直到 Run 进入终态。"""

    for _ in range(100):
        response = await client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        await asyncio.sleep(0)
    raise AssertionError("Run 未在测试等待期间进入终态")


def make_client(manager: RunManager) -> httpx.AsyncClient:
    """创建直接调用 ASGI 应用的异步测试客户端。"""

    transport = httpx.ASGITransport(app=create_app(manager))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_create_run_returns_immediately_and_completes_in_background() -> None:
    manager = RunManager(SuccessfulAgent())
    try:
        async with make_client(manager) as client:
            response = await client.post(
                "/api/threads/thread-1/runs",
                json={"message": "你好", "user_id": "user-1"},
            )

            assert response.status_code == 202
            created = response.json()
            assert created["status"] in {"queued", "running", "completed"}

            completed = await wait_for_terminal_run(client, created["run_id"])
            assert completed["status"] == "completed"
            assert completed["output"] == "收到：你好"
            assert completed["thread_id"] == "thread-1"
    finally:
        await manager.aclose()


@pytest.mark.anyio
async def test_failed_agent_run_is_queryable() -> None:
    manager = RunManager(FailingAgent())
    try:
        async with make_client(manager) as client:
            response = await client.post(
                "/api/threads/thread-2/runs",
                json={"message": "触发失败"},
            )
            failed = await wait_for_terminal_run(client, response.json()["run_id"])

            assert failed["status"] == "failed"
            assert failed["error"] == "模型暂时不可用"
    finally:
        await manager.aclose()


@pytest.mark.anyio
async def test_unknown_run_returns_404() -> None:
    manager = RunManager(SuccessfulAgent())
    try:
        async with make_client(manager) as client:
            response = await client.get("/api/runs/not-found")
        assert response.status_code == 404
    finally:
        await manager.aclose()
