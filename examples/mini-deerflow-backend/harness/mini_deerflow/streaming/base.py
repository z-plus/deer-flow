"""流桥接器的公共契约与控制消息。"""

from __future__ import annotations

import abc
import json
import math
from collections.abc import AsyncIterator
from dataclasses import dataclass, asdict
from typing import Any

DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 15.0
MAX_HEARTBEAT_INTERVAL_SECONDS = 300.0

@dataclass(frozen=True)
class StreamEvent:
    """统一流式输出事件"""

    id: str
    event: str
    data: Any

@dataclass(frozen=True)
class StreamGap:
    """流式输出的间隙，用来判断请求的游标已经早于当前窗口保留的数据，是的话无法重获取该流式数据"""
    # Q请求发送过来的事件ID
    requested_event_id: str | None
    # 服务端当前仍然保留的最早事件 ID。
    earliest_available_event_id: str | None
    # 服务端当前仍然保留的最新事件 ID。
    latest_available_event_id: str | None


# 心跳机制，用于保活，防止大模型过长事件没有输出，导致sse断开
HEARTBEAT_SENTINEL = StreamEvent(id="", event="__heartbeat__", data=None)
END_SENTINEL = StreamEvent(id="", event="__end__", data=None)
StreamItem = StreamGap | StreamEvent

class StreamBridge(abc.ABC):
    """客户端与Agent流式传输的桥梁抽象类"""

    # 用来判断该桥梁是否支持跨进程共享
    supports_cross_process = False

    def __init__(self,
                 *,
                 heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
                 ) -> None:
        self._heartbeat_interval = self._validate_heartbeat_interval(
            heartbeat_interval
        )

    @property
    def heartbeat_interval(self) -> float:
        return self._heartbeat_interval


    def _resolve_heartbeat_interval(self, value: float | None) -> float:
        # 加载心跳间隔时间的默认配置
        return (
            self._heartbeat_interval
            if value is None
            else DEFAULT_HEARTBEAT_INTERVAL_SECONDS
        )

    @staticmethod
    def _validate_heartbeat_interval(value: float) -> float:
        # 校验心跳间隔时间
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
            or value > MAX_HEARTBEAT_INTERVAL_SECONDS
        ):
            raise ValueError("heartbeat_interval 必须是 0 到 300 之间的有限数字")
        return float(value)

    @abc.abstractmethod
    async def publish(self, run_id: str, event: str, data: Any) -> None: ...

    @abc.abstractmethod
    async def publish_end(self, run_id: str) -> None: ...

    @abc.abstractmethod
    def subscribe(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
        heartbeat_interval: float | None = None,
    ) -> AsyncIterator[StreamItem]: ...

    @abc.abstractmethod
    async def cleanup(self, run_id: str, *, delay: float = 0) -> None: ...

    async def ping(self) -> bool:
        """内存实现没有外部依赖，因此始终可用。"""

        return True

    async def close(self) -> None:
        """释放桥接器资源。"""
