# Mini DeerFlow Backend

这是一个从零复刻 DeerFlow 后端核心思想的教学项目。它不是生产版 DeerFlow，也不会导入现成的 `deerflow.*` 实现；我们会从一个最小 Agent 开始，每一阶段只加入一个新的架构边界。

## 当前状态

启动 Web 服务（在本项目目录执行，模型凭据通过环境变量配置）：

```bash
uv sync --extra dev
uv run mini-deerflow --reload
```

默认监听 `127.0.0.1:8001`，接口文档位于 `/docs`。
可通过 `--host` 和 `--port` 修改监听地址和端口。

当前只完成了项目骨架（阶段 0）：

- 独立 Python 3.12 包
- `harness` 与 `app` 的单向依赖边界
- 不需要 API Key 的确定性假模型 fixture
- 示例配置和离线测试入口

Agent、HTTP API、数据库、沙箱等功能尚未实现。后续阶段会按测试驱动逐步加入。

## 范围

最终示例仅面向单机、单进程学习环境，使用本地 SQLite 和本地 workspace。它不会实现 PostgreSQL/Redis 多实例、Kubernetes、调度任务、IM 渠道、OIDC/PAT 或生产扩展系统。

## 环境与初始命令

本项目是父工程 `backend` uv workspace 的成员，共用 `backend/.venv` 和
`backend/uv.lock`，不要在本目录创建独立虚拟环境或锁文件。要求 Python 3.12+。

首次初始化时，从仓库的 `backend/` 目录运行：

```bash
uv sync
uv run python -c "import mini_deerflow; print(mini_deerflow.__version__)"
uv run pytest ../examples/mini-deerflow-backend/tests -q
```

`uv sync` 会在父工程的 `backend/.venv` 中以可编辑方式安装当前包及模型依赖；
IDE 请选择 `backend/.venv` 作为 Python 解释器。由于是可编辑安装，修改
`harness/mini_deerflow/` 后不需要重新安装即可在代码中导入最新实现。

测试默认离线运行，不读取模型凭据。配置起点见 [`config.example.yaml`](config.example.yaml)。

## 十二个学习阶段

### 调用流式接口

Gateway 启动后，在本项目目录运行：

```bash
uv run python scripts/request_stream.py "请计算 12 + 30"
```

脚本向 `http://127.0.0.1:8001/api/threads/demo-thread/stream` 发送 POST，
逐行打印 SSE。可通过 `--base-url`、`--thread-id`、`--user-id` 指定服务和会话。
Ctrl+C 断开客户端连接；这不会主动取消服务端 Run。

订阅已有 Run（POST `/api/runs/{run_id}/stream`，不传请求体）：

```bash
uv run python scripts/request_stream.py --run-id YOUR_RUN_ID
uv run python scripts/request_stream.py --run-id YOUR_RUN_ID --last-event-id 7
```

也可以使用专门的已有 Run 订阅脚本：

```bash
uv run python scripts/request_run_stream.py YOUR_RUN_ID
uv run python scripts/request_run_stream.py YOUR_RUN_ID --last-event-id 7
```

`--last-event-id` 通过 `Last-Event-ID` 请求头传给服务端，用于断线续传。

| 阶段 | 交付结果 | 主要生产代码映射 |
| --- | --- | --- |
| 1 | 最小工具调用 Agent | [`lead_agent/agent.py`](../../backend/packages/harness/deerflow/agents/lead_agent/agent.py) |
| 2 | 显式 StateGraph 与 reducer | [`thread_state.py`](../../backend/packages/harness/deerflow/agents/thread_state.py) |
| 3 | thread 与 checkpoint | [`runtime/checkpointer/`](../../backend/packages/harness/deerflow/runtime/checkpointer/) |
| 4 | FastAPI 与异步 Run | [`runtime/runs/manager.py`](../../backend/packages/harness/deerflow/runtime/runs/manager.py) |
| 5 | SSE、取消、StreamBridge | [`runtime/stream_bridge/`](../../backend/packages/harness/deerflow/runtime/stream_bridge/) |
| 6 | 错误、循环、Token、摘要中间件 | [`agents/middlewares/`](../../backend/packages/harness/deerflow/agents/middlewares/) |
| 7 | thread workspace 与文件工具 | [`sandbox/`](../../backend/packages/harness/deerflow/sandbox/) |
| 8 | SQLite Run/Event 与事件重放 | [`runtime/events/`](../../backend/packages/harness/deerflow/runtime/events/) |
| 9 | Skills | [`skills/`](../../backend/packages/harness/deerflow/skills/) |
| 10 | MCP 工具 | [`mcp/`](../../backend/packages/harness/deerflow/mcp/) |
| 11 | 同步 Subagent | [`subagents/`](../../backend/packages/harness/deerflow/subagents/) |
| 12 | 本地认证与显式长期记忆 | [`agents/memory/`](../../backend/packages/harness/deerflow/agents/memory/) |

## 目录边界

```text
harness/                   # Python 包源码根目录
`-- mini_deerflow/         # 可复用能力；导入名为 mini_deerflow
    |-- learning_stages.py # 十二阶段与目标包的机器可读清单
    |-- agents/            # 1-2: Agent 与显式状态图
    |-- models/            # 1: 模型构造
    |-- tools/             # 1, 7: 内置工具
    |-- checkpoints/       # 3: thread checkpoint
    |-- runtime/           # 4-5: Run 生命周期与取消
    |-- streaming/         # 5: 事件流与 SSE 桥接
    |-- middleware/        # 6: 运行中间件
    |-- sandbox/           # 7: thread workspace
    |-- persistence/       # 8: SQLite Run/Event
    |-- skills/            # 9: Skills
    |-- mcp/               # 10: MCP
    |-- subagents/         # 11: Subagent
    `-- memory/            # 12: 长期记忆
app/                       # 应用适配层；可以导入 mini_deerflow
    |-- gateway/           # 4: FastAPI 组装与生命周期
    |-- routers/           # 4-5, 7: HTTP/SSE/上传接口
    `-- auth/              # 12: 本地认证
```

调用方使用 `from mini_deerflow.models import create_chat_model`，不需要在导入路径中出现 `harness`。这些包现在只声明职责，不包含未来阶段的业务实现。边界测试会扫描 `mini_deerflow` 的 Python import，阻止它反向依赖 `app`。这与 DeerFlow 的 Harness/App 分层一致。

## 阶段 0 验收

从仓库的 `backend/` 目录运行：

```bash
uv run pytest ../examples/mini-deerflow-backend/tests -q
```

验收问题：

1. 为什么 `harness` 不应该导入 `app`？
2. 为什么基础测试不调用真实模型？
3. 为什么这里维护一份逐步演进的代码，而不是复制十二套阶段目录？

答案应分别涉及可复用运行层、测试确定性，以及避免多份实现漂移。
