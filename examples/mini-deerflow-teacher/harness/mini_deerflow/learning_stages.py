from dataclasses import dataclass


@dataclass(frozen=True)
class LearningStage:
    number: int
    name: str
    packages: tuple[str, ...]


LEARNING_STAGES = (
    LearningStage(1, "minimal-agent", ("agents", "models", "tools")),
    LearningStage(2, "agent-state-and-reducer", ("agents",)),
    LearningStage(3, "threads-and-checkpoints", ("checkpoints",)),
    LearningStage(4, "gateway-and-runs", ("runtime",)),
    LearningStage(5, "sse-and-cancellation", ("streaming", "runtime")),
    LearningStage(6, "middleware", ("middleware",)),
    LearningStage(7, "thread-workspace", ("sandbox", "tools")),
    LearningStage(8, "durable-runs-and-events", ("persistence",)),
    LearningStage(9, "skills", ("skills",)),
    LearningStage(10, "mcp", ("mcp",)),
    LearningStage(11, "subagents", ("subagents",)),
    LearningStage(12, "auth-and-memory", ("memory",)),
)
