"""FastAPI 应用的组装入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import create_runs_router
from mini_deerflow.runtime import RunManager


def create_app(manager: RunManager) -> FastAPI:
    """组装 Mini DeerFlow FastAPI 应用。

    manager 由应用外部创建并注入。这里不创建模型和 Agent，使 Gateway
    只承担应用组装职责。
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # yield 之前是启动阶段；本阶段没有额外启动资源。
        yield
        # yield 之后是关闭阶段，确保残留后台任务不会泄漏到进程退出之后。
        await manager.aclose()

    app = FastAPI(title="Mini DeerFlow Teacher", lifespan=lifespan)
    # 路由通过同一个 Manager 共享 Run 状态和后台任务集合。
    app.include_router(create_runs_router(manager))
    return app
