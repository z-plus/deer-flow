"""后台 Agent 与 HTTP SSE 响应之间的内存事件桥。"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StreamEvent:
    """一条可发送给客户端的 Run 事件。"""

    event_id: int
    event: str
    data: dict[str, Any]


class MemoryStreamBridge:
    """在单进程内发布并订阅 Run 事件。

    历史列表让客户端在 Run 已经开始后仍能读到之前的事件；每个订阅者拥有
    独立队列，因此一个慢客户端不会取走另一个客户端的数据。
    """

    def __init__(self) -> None:
        self._history: dict[str, list[StreamEvent]] = defaultdict(list)
        self._subscribers: dict[str, set[asyncio.Queue[StreamEvent]]] = defaultdict(set)
        self._ended: set[str] = set()
        self._lock = asyncio.Lock()

    async def publish(self, run_id: str, event: str, data: dict[str, Any]) -> None:
        """保存事件，并把它广播给当前所有订阅者。"""

        async with self._lock:
            item = StreamEvent(len(self._history[run_id]) + 1, event, data)
            self._history[run_id].append(item)
            for queue in self._subscribers[run_id]:
                queue.put_nowait(item)

    async def finish(self, run_id: str) -> None:
        """发布内部结束事件，使所有 SSE 消费者正常退出。"""

        async with self._lock:
            if run_id in self._ended:
                return
            self._ended.add(run_id)
            item = StreamEvent(len(self._history[run_id]) + 1, "end", {})
            self._history[run_id].append(item)
            for queue in self._subscribers[run_id]:
                queue.put_nowait(item)

    async def subscribe(self, run_id: str) -> AsyncIterator[StreamEvent]:
        """先重放已有事件，再持续等待新事件，直到收到 end。"""

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
                return

            while True:
                item = await queue.get()
                yield item
                if item.event == "end":
                    return
        finally:
            async with self._lock:
                self._subscribers[run_id].discard(queue)
