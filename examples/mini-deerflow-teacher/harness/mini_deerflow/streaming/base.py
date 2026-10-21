"""流桥接器的公共契约与控制消息。"""

from __future__ import annotations

import abc
import math
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 15.0
MAX_HEARTBEAT_INTERVAL_SECONDS = 300.0


@dataclass(frozen=True)
class StreamEvent:
    """一条可重放的流事件。"""

    id: str
    event: str
    data: Any


@dataclass(frozen=True)
class StreamGap:
    """请求的游标已经早于当前保留窗口，无法完整重放。"""

    requested_event_id: str | None
    earliest_available_event_id: str | None
    latest_available_event_id: str | None


# 哨兵属于内部控制消息，不占用普通事件 ID，也不写入事件日志。
HEARTBEAT_SENTINEL = StreamEvent(id="", event="__heartbeat__", data=None)
END_SENTINEL = StreamEvent(id="", event="__end__", data=None)
StreamItem = StreamEvent | StreamGap


class StreamBridge(abc.ABC):
    """后台生产者和流式消费者之间的抽象接口。"""

    supports_cross_process = False

    def __init__(
        self,
        *,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        self._heartbeat_interval = self._validate_heartbeat_interval(
            heartbeat_interval
        )

    @property
    def heartbeat_interval(self) -> float:
        return self._heartbeat_interval

    def _resolve_heartbeat_interval(self, value: float | None) -> float:
        return (
            self._heartbeat_interval
            if value is None
            else self._validate_heartbeat_interval(value)
        )

    @staticmethod
    def _validate_heartbeat_interval(value: float) -> float:
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
