"""Gateway 服务依赖的统一获取入口。

真实 DeerFlow 在 lifespan 中把运行时服务保存到 ``app.state``，路由再按请求
取出同一个服务实例。教学项目保留这条核心流程，只省略生产版的复杂依赖。
"""

from typing import Callable, TypeVar, cast

from fastapi import HTTPException, Request

from mini_deerflow.runtime import RunManager

T = TypeVar("T")

def _require(attr: str, label: str) -> Callable[[Request], T]:
    """创建一个从 ``request.app.state`` 读取服务的依赖函数。"""

    def dependency(request: Request) -> T:
        value = getattr(request.app.state, attr, None)
        if value is None:
            raise HTTPException(status_code=503, detail=f"{label} 尚未初始化")
        return cast(T, value)

    return dependency

# 路由通过这个函数获取 lifespan 创建的全局 RunManager。
get_run_manager: Callable[[Request], RunManager] = _require(
    "run_manager",
    "RunManager",
)