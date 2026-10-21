"""早期教学版的简单内存 StreamBridge。

这个实现保留阶段 5 最初使用的结构：

- ``_history`` 保存每个 Run 的全部历史事件；
- ``_subscribers`` 为每个在线订阅者创建独立队列；
- ``_ended`` 记录已经结束的 Run。

它适合用来理解“生产者发布、消费者订阅”的基本流程，但不适合生产环境：
历史和订阅队列都没有容量限制，也不支持 Last-Event-ID、StreamGap 和心跳。
完整版请使用同目录 ``bridge.py`` 中的 ``MemoryStreamBridge``。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from .base import END_SENTINEL, StreamBridge, StreamEvent, StreamItem


class SimpleMemoryStreamBridge(StreamBridge):
    """用于教学对比的简单内存事件桥。"""

    def __init__(self) -> None:
        super().__init__()
        # 保存每个 Run 的全部事件，晚连接的客户端可以从头重放。
        self._history: dict[str, list[StreamEvent]] = defaultdict(list)
        # 每个订阅者拥有自己的队列，因此多个客户端不会互相抢走事件。
        self._subscribers: dict[
            str,
            set[asyncio.Queue[StreamEvent]],
        ] = defaultdict(set)
        # 记录已经结束的 Run，保证结束操作幂等，并处理结束后的晚订阅。
        self._ended: set[str] = set()
        # 保护三个共享容器，避免发布、订阅和清理同时修改它们。
        self._lock = asyncio.Lock()

    async def publish(self, run_id: str, event: str, data: Any) -> None:
        """保存一条事件，并复制到该 Run 的所有在线订阅队列。"""

        async with self._lock:
            item = StreamEvent(
                id=str(len(self._history[run_id]) + 1),
                event=event,
                data=data,
            )
            self._history[run_id].append(item)
            for queue in self._subscribers[run_id]:
                queue.put_nowait(item)

    async def publish_end(self, run_id: str) -> None:
        """幂等地结束 Run，并通知当前所有订阅者退出。"""

        async with self._lock:
            if run_id in self._ended:
                return
            self._ended.add(run_id)
            for queue in self._subscribers[run_id]:
                queue.put_nowait(END_SENTINEL)

    async def subscribe(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
        heartbeat_interval: float | None = None,
    ) -> AsyncIterator[StreamItem]:
        """从头重放历史，然后等待新事件直到 Run 结束。

        参数保留是为了符合 ``StreamBridge`` 契约，但这个早期版本不会使用
        ``last_event_id`` 和 ``heartbeat_interval``。
        """

        del last_event_id, heartbeat_interval
        queue: asyncio.Queue[StreamEvent] = asyncio.Queue()
        async with self._lock:
            history = list(self._history[run_id])
            ended = run_id in self._ended
            if not ended:
                self._subscribers[run_id].add(queue)

        try:
            for item in history:
                yield item
            if ended:
                yield END_SENTINEL
                return

            while True:
                item = await queue.get()
                yield item
                if item is END_SENTINEL:
                    return
        finally:
            async with self._lock:
                self._subscribers[run_id].discard(queue)

    async def cleanup(self, run_id: str, *, delay: float = 0) -> None:
        """删除一个 Run 的历史、订阅集合和结束标记。"""

        if delay > 0:
            await asyncio.sleep(delay)
        async with self._lock:
            queues = tuple(self._subscribers.pop(run_id, ()))
            self._history.pop(run_id, None)
            self._ended.discard(run_id)
            # 唤醒清理前仍在等待的消费者，避免它们永久阻塞。
            for queue in queues:
                queue.put_nowait(END_SENTINEL)

    async def close(self) -> None:
        """关闭时清理所有已知 Run。"""

        run_ids = set(self._history) | set(self._subscribers) | self._ended
        for run_id in tuple(run_ids):
            await self.cleanup(run_id)
