"""后台 Agent 与 HTTP SSE 响应之间的内存事件桥。"""

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
    """一个Run的事件日志、同步条件和生命周期"""

    # run 的事件列表
    events: list[StreamEvent] = field(default_factory=list)
    # 用于协调当前这个订阅run的流式线程
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    # 判断当前这个Run的流是否结束
    ended: bool = False
    # events[0] 在完整事件序列中的绝对位置。开始游标
    start_offset: int = 0
    # cleanup 后旧订阅器仍持有此对象，retired 用于通知它停止读取。是否继续尝试读取的flag, True 标识不用再测试了
    retired: bool = False


# 本地换成的流式桥梁
class MemoryStreamBridge(StreamBridge):
    """在本地缓存的进程内构建一个消息队列，对 run事件订阅

    历史列表人客户端在 Run开始后仍然能够读到之前的事件，每个订阅者拥有独立的队列
    因此一个慢客户端不会取走另外一个客户端的数据
    """

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
        # 如果Run没有创建订阅频道，则创建，有就返回之前的
        if run_id not in self._streams:
            self._streams[run_id] = _RunStream()
            self._counters[run_id] = 0
        return self._streams[run_id]

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

    def _resolve_start_offset(self, stream: _RunStream, last_event_id: str | None) -> int | StreamGap:
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
            return StreamGap(requested_event_id=last_event_id, earliest_available_event_id=None, latest_available_event_id=None)

        # 未传递最后的事件ID，动作第一次接收流式信息
        if last_event_id is None:
            return stream.start_offset

        # 事件 ID 的格式是“毫秒时间戳-绝对序号”。这里只取绝对序号，以便
        # 不遍历事件列表就能计算它在当前保留窗口中的位置。
        # 如果取不出来当做首次接收流式信息处理
        sequence = self._parse_sequence(last_event_id)
        if sequence is not None:
            if sequence < stream.start_offset:
                return self._make_gap(stream, last_event_id)

            # events 只保存窗口内的数据，所以要用绝对序号减去窗口起点，
            # 才能得到 Python 列表下标。
            local_index = sequence - stream.start_offset

            # 判断获取到的下标中的 id 与当前传递的ID相同，防止伪造ID，导致数据串掉
            if (0 <= local_index < len(stream.events)
                and stream.events[local_index].id == last_event_id):
                # Last-Event-ID 对应的事件已经被客户端收到，所以返回下一条
                # 事件的绝对偏移量，避免断线重连后重复发送最后一条事件。
                return sequence + 1

        if stream.events:
            logger.warning(
                "事件游标 %s 不在保留窗口内，将从最早事件重放",
                last_event_id,
            )

        # 如果当前没有事件，start_offset 仍表示下一条新事件将采用的绝对
        # 位置；订阅循环会在这个位置等待 publish() 或 publish_end()。
        return stream.start_offset

    # 订阅频道，并推送事件
    async def subscribe(        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
        heartbeat_interval: float | None = None,) -> AsyncIterator[StreamItem]:
        """
        创建RUN的流式订阅频道，并实时推送消息， "从游标之后消费事件，并在空闲时产生心跳。
        Args:
            run_id: RUN 的 ID
            last_event_id:  最后一次接收事件的ID，为接收过填None
            heartbeat_interval: 心跳间隔事件

        Returns: 流式事件

        """

        # 创建一个心跳间隔时间
        heartbeat = self._resolve_heartbeat_interval(heartbeat_interval)
        stream = self._get_or_create_stream(run_id)
        async with stream.condition:
            # 获取到当前可以获取event的游标的位置，或者StreamGap
            start = self._resolve_start_offset(stream, last_event_id)
            if isinstance(start, StreamGap):
                gap: StreamGap | None = start
                # 如果是StreamGap，表明历史获取的event id 早于现在窗口id，已经无法重放，直接从新的位置重放
                next_offset = stream.start_offset
            else:
                gap: StreamGap | None = None
                next_offset = start
        if gap is not None:
            yield gap
            return

        cursor_event_id = last_event_id

        while True:
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
                elif next_offset < stream.start_offset:
                    # 订阅者处理速度可能赶不上生产者。若它等待的绝对位置已经
                    # 小于保留窗口起点，说明未读事件刚刚被有界日志裁剪。
                    item = self._make_gap(stream, cursor_event_id)
                    should_stop = True
                else:
                    # 将绝对偏移转换成当前 events 列表下标。例如窗口从绝对
                    # 位置 100 开始，那么 next_offset=102 对应 local_index=2。
                    # local_index 不是历史全部event的索引位置，是当前stream.event 窗口中的偏移量
                    local_index = next_offset - stream.start_offset
                    if 0 <= local_index < len(stream.events):
                        item = stream.events[local_index]
                        next_offset += 1
                        cursor_event_id = item.id
                    elif stream.ended:
                        item = END_SENTINEL
                    else:

                        try:
                            # 当前没有可读事件，但 Run 尚未结束。wait() 会原子地
                            # 释放 Condition 锁，让 publish()/publish_end()/cleanup()
                            # 能修改状态；被唤醒时会重新取得锁。
                            await asyncio.wait_for(
                                stream.condition.wait(),
                                timeout=heartbeat
                            )
                        except TimeoutError:
                            item = HEARTBEAT_SENTINEL
                        else:
                            continue

            yield item

            # 如果item结束，或结束标识为true
            if item is END_SENTINEL or should_stop:
                return

    def _next_id(self, run_id: str) -> str:
        """生成“毫秒时间戳-Run 内序号”形式的单调事件 ID。"""
        # 每个run的event是单线程发布，不存在多线程竞争一个序列号的问题，不需要加锁
        sequence = self._counters.get(run_id, 0)
        self._counters[run_id] = sequence + 1
        return f"{int(time.time() * 1000)}-{sequence}"

    async def publish(self, run_id: str, event: str, data: Any) -> None:
        # event是单线程发布，不存在多线程竞争一个序列号的问题
        stream = self._get_or_create_stream(run_id)
        entry = StreamEvent(id=self._next_id(run_id), event=event, data=data)
        async with stream.condition:
            stream.events.append(entry)
            if len(stream.events) > self._maxsize:
                # 如果当前事件列表的长度大于最大值，则需要滑动窗口
                overflow = len(stream.events) - self._maxsize
                # 删除列表超出的历史数据，保留新的数据
                del stream.events[:overflow]
                # 移动开始游标到跳过的位置
                stream.start_offset += overflow
            stream.condition.notify_all()

    async def publish_end(self, run_id: str) -> None:
        """幂等地结束事件流并唤醒全部等待者。"""
        stream = self._get_or_create_stream(run_id)
        async with stream.condition:
            stream.ended = True
            # 唤醒所有消费者，告诉他们 stream 已经 end = True 可以退出消费
            stream.condition.notify_all()

    async def cleanup(self, run_id: str, *, delay: float = 0) -> None:
        """回收 Run 的日志，并可靠唤醒仍持有旧流对象的订阅者。
        等待一段时间再清理 _RunStream，主要是为了给尚未消费完、晚到或正在重连的客户端保留一个短暂的读取窗口。
        """
        if delay > 0:
            await asyncio.sleep(delay)
        stream = self._get_or_create_stream(run_id)
        if stream is None:
            return
        async with stream.condition:
            stream.retired = True
            stream.events.clear()
            # 二次校验，防止在处理clear的过程中，创建了新的流，替换旧的流，导致误删
            if self._streams.get(run_id) is stream:
                self._streams.pop(run_id, None)
                self._counters.pop(run_id, None)
            stream.condition.notify_all()


    async def close(self) -> None:
        """关闭所有Gateway创建的 RUN"""
        for run_id in tuple(self._streams):
            await self.cleanup(run_id)


