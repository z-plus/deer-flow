# Mini DeerFlow Teacher

这是一个从零学习 DeerFlow 后端核心思想的教学项目，以
`examples/mini-deerflow-backend` 为参照。发行包名为 `mini-deerflow-teacher`，
Python 导入包与目标项目一致，使用 `mini_deerflow`。

## 当前进度：阶段 4（FastAPI 与异步 Run）

- Python 3.12 `harness/mini_deerflow` 布局
- `harness` 与 `app` 的单向依赖边界
- 不需要 API Key 的确定性假模型
- 十二个学习阶段的机器可读清单
- 最小的 `模型 → 工具 → 模型` Agent 循环
- 未知工具拒绝和最大步数保护
- 使用 LangChain `create_agent()` 创建 Agent 图
- `ThreadState` 继承 `AgentState` 的消息及 reducer 能力
- 使用 `thread_id` 恢复同一会话的状态
- 不同 thread 的消息历史彼此隔离
- FastAPI 创建和查询 Run 的接口
- 后台执行 Agent，HTTP 请求立即返回 `run_id`
- `queued → running → completed/failed` 生命周期

教学讲义与阶段考试：

- [`docs/stage-01-minimal-agent.md`](docs/stage-01-minimal-agent.md)
- [`docs/stage-02-agent-state.md`](docs/stage-02-agent-state.md)
- [`docs/stage-03-thread-checkpoints.md`](docs/stage-03-thread-checkpoints.md)
- [`docs/stage-04-fastapi-async-runs.md`](docs/stage-04-fastapi-async-runs.md)

## 运行阶段 4 测试

在仓库根目录执行：

```powershell
backend\.venv\Scripts\python.exe -m pytest examples\mini-deerflow-teacher\tests -q
```

如果尚未创建父工程虚拟环境，请先进入 `backend` 执行 `uv sync`。

## 架构约束

`harness` 是可复用运行层，不得导入应用适配层 `app`；`app` 可以调用
`mini_deerflow`。调用方可以直接使用：

```python
from mini_deerflow.agents import run_agent
from mini_deerflow.agents import build_agent_graph  # 内部使用 create_agent()
from mini_deerflow.checkpoints import create_memory_checkpointer, thread_config
from mini_deerflow.models import create_chat_model
from mini_deerflow.tools import add
```

测试会自动扫描并保护这条边界。
