from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass
class FakeModel:
    """Credential-free scripted model shared by later learning stages."""

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

