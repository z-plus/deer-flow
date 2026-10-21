"""与 DeerFlow 粒度一致的单进程内存 StreamBridge。"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from .base import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    END_SENTINEL,
    HEARTBEAT_SENTINEL,
    StreamBridge,
    StreamEvent,
    StreamGap,
    StreamItem,
)

logger = logging.getLogger(__name__)
_EVENT_ID_PATTERN = re.compile(r"[0-9]+-([0-9]+)")


@dataclass
class _RunStream:
    """一个 Run 的事件日志、同步条件和生命周期状态。"""

    events: list[StreamEvent] = field(default_factory=list)
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    ended: bool = False
    # events[0] 在完整事件序列中的绝对位置。
    start_offset: int = 0
    # cleanup 后旧订阅器仍持有此对象，retired 用于通知它停止读取。
    retired: bool = False


class MemoryStreamBridge(StreamBridge):
    """使用有界事件日志实现重放、心跳、间隙检测和资源回收。"""

    def __init__(
        self,
        *,
        queue_maxsize: int = 256,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        super().__init__(heartbeat_interval=heartbeat_interval)
        self._maxsize = max(1, queue_maxsize)
        self._streams: dict[str, _RunStream] = {}
        self._counters: dict[str, int] = {}

    def _get_or_create_stream(self, run_id: str) -> _RunStream:
        if run_id not in self._streams:
            self._streams[run_id] = _RunStream()
            self._counters[run_id] = 0
        return self._streams[run_id]

    def _next_id(self, run_id: str) -> str:
        """生成“毫秒时间戳-Run 内序号”形式的单调事件 ID。"""

        sequence = self._counters.get(run_id, 0)
        self._counters[run_id] = sequence + 1
        return f"{int(time.time() * 1000)}-{sequence}"

    @staticmethod
    def _parse_sequence(event_id: str) -> int | None:
        match = _EVENT_ID_PATTERN.fullmatch(event_id)
        if match is None:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _make_gap(
        stream: _RunStream,
        requested_event_id: str | None,
    ) -> StreamGap:
        return StreamGap(
            requested_event_id=requested_event_id,
            earliest_available_event_id=(
                stream.events[0].id if stream.events else None
            ),
            latest_available_event_id=(
                stream.events[-1].id if stream.events else None
            ),
        )

    def _resolve_start_offset(
        self,
        stream: _RunStream,
        last_event_id: str | None,
    ) -> int | StreamGap:
        """计算订阅者下一次应读取的绝对事件偏移量。

        ``last_event_id`` 表示客户端最后成功收到的事件，因此正常情况下应从
        它的下一条事件开始，而不是再次发送该事件。本方法返回两种结果：

        - ``int``：下一条待读事件在完整 Run 事件序列中的绝对偏移量；
        - ``StreamGap``：所需历史已被裁剪，无法保证连续重放。

        这里必须区分两个位置概念：``sequence`` 是事件从 Run 开始计算的
        绝对序号；``local_index`` 是它在当前 ``stream.events`` 列表中的下标。
        当有界日志裁剪旧事件后，二者不再相同。例如 ``start_offset == 100``
        时，绝对序号 100 对应列表下标 0。
        """

        # cleanup() 会把旧的 _RunStream 标记为 retired。此时即使订阅者仍然
        # 持有该对象，也不能再从中恢复事件，因为它的日志已经被释放。
        if stream.retired:
            return StreamGap(last_event_id, None, None)

        # 客户端没有提供 Last-Event-ID，表示这是一次全新订阅。应从当前仍然
        # 保留的最早事件开始读取。start_offset 可能不是 0，因为更早的事件
        # 可能已经受 queue_maxsize 限制而被裁剪。
        if last_event_id is None:
            return stream.start_offset

        # 事件 ID 的格式是“毫秒时间戳-绝对序号”。这里只取绝对序号，以便
        # 不遍历事件列表就能计算它在当前保留窗口中的位置。
        sequence = self._parse_sequence(last_event_id)
        if sequence is not None:
            # 客户端游标早于当前保留窗口，说明游标之后至少有一部分事件已经
            # 被裁剪。此时不能只返回剩余事件，否则客户端会误以为重放完整。
            if sequence < stream.start_offset:
                return self._make_gap(stream, last_event_id)

            # events 只保存窗口内的数据，所以要用绝对序号减去窗口起点，
            # 才能得到 Python 列表下标。
            local_index = sequence - stream.start_offset

            # 不能只相信序号：还要比较完整事件 ID，防止另一个 Run 的 ID、
            # 时间戳被修改的 ID 或伪造 ID 恰好带有相同序号。
            if (
                0 <= local_index < len(stream.events)
                and stream.events[local_index].id == last_event_id
            ):
                # Last-Event-ID 对应的事件已经被客户端收到，所以返回下一条
                # 事件的绝对偏移量，避免断线重连后重复发送最后一条事件。
                return sequence + 1

        # 到这里说明游标格式无效，或虽然序号还在窗口范围内，但完整 ID 与
        # 对应事件不匹配。它不一定代表数据已经丢失，因此采用保守策略：
        # 从当前最早的保留事件重新发送，而不是静默跳过可能未消费的数据。
        if stream.events:
            logger.warning(
                "事件游标 %s 不在保留窗口内，将从最早事件重放",
                last_event_id,
            )

        # 如果当前没有事件，start_offset 仍表示下一条新事件将采用的绝对
        # 位置；订阅循环会在这个位置等待 publish() 或 publish_end()。
        return stream.start_offset

    async def stream_exists(self, run_id: str) -> bool:
        return run_id in self._streams

    async def publish(self, run_id: str, event: str, data: Any) -> None:
        stream = self._get_or_create_stream(run_id)
        entry = StreamEvent(id=self._next_id(run_id), event=event, data=data)
        async with stream.condition:
            stream.events.append(entry)
            if len(stream.events) > self._maxsize:
                overflow = len(stream.events) - self._maxsize
                del stream.events[:overflow]
                stream.start_offset += overflow
            stream.condition.notify_all()

    async def publish_end(self, run_id: str) -> None:
        """幂等地结束事件流并唤醒全部等待者。"""

        stream = self._get_or_create_stream(run_id)
        async with stream.condition:
            stream.ended = True
            stream.condition.notify_all()

    async def subscribe(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
        heartbeat_interval: float | None = None,
    ) -> AsyncIterator[StreamItem]:
        """订阅一个 Run，从指定游标之后持续产出事件。

        这是一个异步生成器。调用它不会一次性返回所有结果；调用方通过
        ``async for`` 每次取得一条 ``StreamEvent``、``StreamGap`` 或控制
        哨兵，直到 Run 结束、历史出现缺口，或者流被清理。

        ``last_event_id`` 通常来自 SSE 的 ``Last-Event-ID`` 请求头，表示
        客户端最后成功收到的事件。没有提供时，从当前保留窗口的最早事件
        开始；提供且仍可确认时，从它的下一条事件继续。

        ``heartbeat_interval`` 控制没有新事件时多久产生一次心跳。它只维持
        连接活跃，不改变 Run 状态，也不会推进事件读取游标。
        """

        # 优先使用调用方指定的心跳间隔；没有指定时使用 Bridge 默认值。
        # _resolve_heartbeat_interval() 同时负责拒绝 0、负数、无穷大等配置。
        heartbeat = self._resolve_heartbeat_interval(heartbeat_interval)

        # Run 可能在 SSE 订阅建立前就已经发布了事件，因此这里取得的是
        # 与生产者共享的事件日志，而不是为订阅者创建一份新的事件队列。
        stream = self._get_or_create_stream(run_id)

        # 计算初始游标期间必须持有 Condition 内部锁，防止 publish() 或
        # cleanup() 同时裁剪/清空日志，导致 start_offset 与 events 不一致。
        async with stream.condition:
            start = self._resolve_start_offset(stream, last_event_id)
            if isinstance(start, StreamGap):
                # 初次连接时就发现客户端所需历史已经被裁剪。保存 gap，离开
                # 锁后再 yield，避免调用方处理事件期间一直占用 Condition。
                gap: StreamGap | None = start
                next_offset = stream.start_offset
            else:
                gap = None
                # next_offset 是完整 Run 事件序列中的绝对读取位置，不是当前
                # events 列表下标；后者还需要减去 stream.start_offset。
                next_offset = start

        # 无法连续重放时只返回一条 StreamGap，然后结束本次订阅。客户端应
        # 重新读取持久化 Run/Thread 状态，而不是继续拼接不完整的增量事件。
        if gap is not None:
            yield gap
            return

        # 保存最近成功发送的真实事件 ID。如果在线消费者由于处理太慢而落后
        # 于保留窗口，StreamGap 会通过该字段说明它最后读到了哪里。
        cursor_event_id = last_event_id
        while True:
            # 每轮都重新取得锁并检查真实状态。Condition 唤醒只代表“状态可能
            # 改变”，并不保证一定有新事件，因此不能在 wait() 后直接读取。
            async with stream.condition:
                should_stop = False

                # cleanup() 会将旧流标记为 retired 并唤醒等待者。订阅者已经
                # 消费到末尾且生产者正常结束时返回 END；否则返回 Gap，表示
                # 内存日志被释放后已无法证明事件序列完整。
                if stream.retired:
                    item: StreamItem = (
                        END_SENTINEL
                        if stream.ended and next_offset >= stream.start_offset
                        else StreamGap(cursor_event_id, None, None)
                    )
                    should_stop = True

                # 订阅者处理速度可能赶不上生产者。若它等待的绝对位置已经
                # 小于保留窗口起点，说明未读事件刚刚被有界日志裁剪。
                elif next_offset < stream.start_offset:
                    item = self._make_gap(stream, cursor_event_id)
                    should_stop = True
                else:
                    # 将绝对偏移转换成当前 events 列表下标。例如窗口从绝对
                    # 位置 100 开始，那么 next_offset=102 对应 local_index=2。
                    local_index = next_offset - stream.start_offset
                    if 0 <= local_index < len(stream.events):
                        # 当前游标位置有事件：取出后立即推进绝对偏移，并记录
                        # 已交付事件 ID，下一轮不会重复发送同一事件。
                        item = stream.events[local_index]
                        next_offset += 1
                        cursor_event_id = item.id
                    elif stream.ended:
                        # 已经读完全部保留事件，而且生产者声明不会再发布数据。
                        item = END_SENTINEL
                    else:
                        # 当前没有可读事件，但 Run 尚未结束。wait() 会原子地
                        # 释放 Condition 锁，让 publish()/publish_end()/cleanup()
                        # 能修改状态；被唤醒时会重新取得锁。
                        try:
                            await asyncio.wait_for(
                                stream.condition.wait(),
                                timeout=heartbeat,
                            )
                        except TimeoutError:
                            # 心跳不写入历史，也不推进 next_offset。它只是告诉
                            # SSE 客户端和中间代理：连接仍然存活。
                            item = HEARTBEAT_SENTINEL
                        else:
                            # notify_all() 可能来自发布、结束或清理，也可能多个
                            # 消费者同时被唤醒，所以回到循环顶部重新判断状态。
                            continue

            # yield 必须位于锁外：客户端发送速度可能很慢，若持锁发送 SSE，
            # 会阻塞生产者发布事件，也会阻塞其他订阅者读取同一个 Run。
            yield item

            # END 表示正常读完；should_stop 表示 Gap 或 retired。心跳和普通
            # StreamEvent 不结束订阅，下一轮继续使用自己的 next_offset。
            if item is END_SENTINEL or should_stop:
                return

    async def cleanup(self, run_id: str, *, delay: float = 0) -> None:
        """回收 Run 的日志，并可靠唤醒仍持有旧流对象的订阅者。"""

        if delay > 0:
            await asyncio.sleep(delay)
        stream = self._streams.get(run_id)
        if stream is None:
            return
        async with stream.condition:
            stream.retired = True
            stream.start_offset += len(stream.events)
            stream.events.clear()
            if self._streams.get(run_id) is stream:
                self._streams.pop(run_id, None)
                self._counters.pop(run_id, None)
            stream.condition.notify_all()

    async def close(self) -> None:
        """关闭 Gateway 时清理所有 Run 流。"""

        for run_id in tuple(self._streams):
            await self.cleanup(run_id)
