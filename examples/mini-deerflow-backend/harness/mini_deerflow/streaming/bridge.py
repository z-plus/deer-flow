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
