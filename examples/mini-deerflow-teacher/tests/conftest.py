from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass
class FakeModel:
    """无需凭据的脚本化模型，用于编写结果确定的测试。"""

    responses: deque[Any] = field(default_factory=deque)
    requests: list[Any] = field(default_factory=list)

    def invoke(self, messages: Any) -> Any:
        self.requests.append(messages)
        if not self.responses:
            raise AssertionError("FakeModel has no scripted response")
        return self.responses.popleft()


@pytest.fixture
def fake_model() -> FakeModel:
    return FakeModel()
