"""Mini DeerFlow Gateway 的启动、生命周期与路由组装。"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import runs
from mini_deerflow.agents import make_lead_agent
from mini_deerflow.checkpoints import create_memory_checkpointer
from mini_deerflow.models import create_chat_model
from mini_deerflow.runtime import RunManager
from mini_deerflow.streaming import MemoryStreamBridge
from mini_deerflow.tools import add


@asynccontextmanager
async def lifespan(app: FastAPI):
    """按照 DeerFlow 的方式初始化并清理 Gateway 运行时。

    所有需要跨请求共享的对象都在启动时创建一次，并保存到 app.state。
    路由通过 Request 获取这些对象，而不是自行创建或持有全局副本。
    """

    # 1. checkpoint 在整个 Gateway 生命周期内共享，保证同一 thread 的
    # 多次 Run 能恢复之前的消息状态。
    app.state.checkpointer = create_memory_checkpointer()

    # 2. 模型配置只在应用启动时解析。导入路由或创建 FastAPI 对象不会立刻
    # 读取 API Key，也不会连接外部模型服务。
    app.state.model = create_chat_model(
        provider=os.getenv("MINI_DEERFLOW_MODEL_PROVIDER", "openai"),
        name=os.getenv("MINI_DEERFLOW_MODEL_NAME", "gpt-4.1-mini"),
    )

    # 3. 沿用前面阶段的 lead agent，通过 LangChain create_agent() 创建，
    # 不在 Gateway 中重新实现 Agent 循环。
    app.state.agent = make_lead_agent(
        model=app.state.model,
        tools=[add],
        checkpointer=app.state.checkpointer,
    )

    # 4. RunManager 持有同一个 lead agent，负责所有 HTTP Run 的异步执行。
    # StreamBridge 与 RunManager 同属 Gateway 生命周期，所有请求共享同一实例。
    app.state.stream_bridge = MemoryStreamBridge()
    app.state.run_manager = RunManager(app.state.agent, app.state.stream_bridge)

    try:
        # yield 之后 FastAPI 开始接受请求，路由此时可以访问 app.state。
        yield
    finally:
        # 5. Gateway 关闭时先清理仍在执行的 Run，避免后台任务泄漏。
        await app.state.run_manager.aclose()


def create_app() -> FastAPI:
    """创建并配置 FastAPI Gateway；运行时对象由 lifespan 初始化。"""

    app = FastAPI(title="Mini DeerFlow Teacher", lifespan=lifespan)
    # 与 DeerFlow 一致：直接挂载各路由模块公开的 router 对象。
    app.include_router(runs.router)
    return app


# Uvicorn 使用的模块级 ASGI 应用，例如：uvicorn app.gateway.app:app
app = create_app()
