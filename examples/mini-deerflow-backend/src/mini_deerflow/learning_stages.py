from dataclasses import dataclass


@dataclass(frozen=True)
class LearningStage:
    number: int
    name: str
    packages: tuple[str, ...]


LEARNING_STAGES = (
    LearningStage(1, "minimal-agent", ("harness.agents", "harness.models", "harness.tools")),
    LearningStage(2, "explicit-state-graph", ("harness.agents",)),
    LearningStage(3, "threads-and-checkpoints", ("harness.checkpoints",)),
    LearningStage(4, "gateway-and-runs", ("app.gateway", "app.routers", "harness.runtime")),
    LearningStage(5, "sse-and-cancellation", ("harness.streaming", "harness.runtime")),
    LearningStage(6, "middleware", ("harness.middleware",)),
    LearningStage(7, "thread-workspace", ("harness.sandbox", "harness.tools")),
    LearningStage(8, "durable-runs-and-events", ("harness.persistence",)),
    LearningStage(9, "skills", ("harness.skills",)),
    LearningStage(10, "mcp", ("harness.mcp",)),
    LearningStage(11, "subagents", ("harness.subagents",)),
    LearningStage(12, "auth-and-memory", ("app.auth", "harness.memory")),
)

