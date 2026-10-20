"""Mini DeerFlow Gateway 的启动、生命周期与路由组装。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from langgraph.checkpoint.memory import InMemorySaver

from app.routers import runs
from mini_deerflow.agents import make_lead_agent
from mini_deerflow.models import create_chat_model
from mini_deerflow.runtime import RunManager
from mini_deerflow.tools import add
from dotenv import load_dotenv

@asynccontextmanager
async def lifespan(app: FastAPI):
    """按照 DeerFlow 的方式初始化并清理 Gateway 运行时。

    所有需要跨请求共享的对象都在启动时创建一次，并保存到 app.state。
    路由通过 Request 获取这些对象，而不是自行创建或持有全局副本。
    """
    load_dotenv(override=True)
    # 1. checkpoint 在整个gateway生命周期中共享，保证能够正确回复agent状态
    app.state.checkpointer = InMemorySaver()

    # 2. 创建一个模型，后续不用再传递模型参数
    app.state.model = create_chat_model(model="gpt-5.6-sol", provider="")

    # 3. 沿用前面阶段的 lead agent，通过 LangChain create_agent() 创建，
    # 不在 Gateway 中重新实现 Agent 循环。
    app.state.agent = make_lead_agent(
        model=app.state.model,
        tools=[add],
        checkpointer=app.state.checkpointer,
    )

    # 4. RunManager 持有同一个 lead agent，负责所有 HTTP Run 的异步执行。
    app.state.run_manager = RunManager(app.state.agent)

    try:
        # yield 之后 FastAPI 开始接受请求，路由此时可以访问 app.state。
        yield
    finally:
        # 5. Gateway 关闭时先清理仍在执行的 Run，避免后台任务泄漏。
        await app.state.run_manager.aclose()

def create_app() -> FastAPI:
    """创建并配置 FastAPI Gateway；运行时对象由 lifespan 初始化。"""

    app = FastAPI(title="Mini DeerFlow Backend", lifespan=lifespan)
    # 与 DeerFlow 一致：直接挂载各路由模块公开的 router 对象。
    app.include_router(runs.router)
    return app


# Uvicorn 使用的模块级 ASGI 应用，例如：uvicorn app.gateway.app:app
app = create_app()
