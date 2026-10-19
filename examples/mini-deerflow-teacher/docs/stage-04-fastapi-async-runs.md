# 第四阶段：FastAPI 与异步 Run

## 1. 学习目标

前三个阶段都由 Python 调用方直接执行 Agent。第四阶段增加 HTTP 边界，并把一次 Agent 执行建模为可查询的 Run。

完成本阶段后，你应该能够：

1. 解释为什么长时间 Agent 调用不应阻塞创建请求；
2. 理解 Run 与 thread 的区别；
3. 读懂 Run 的生命周期状态；
4. 理解 `RunManager` 与 FastAPI 路由的职责边界；
5. 使用 `run_id` 查询后台任务结果。

## 本次任务的教学流程

本阶段按照“先领域逻辑，后 HTTP 适配”的顺序学习：

### 第一步：先定义 Run

先不考虑 FastAPI，定义 `RunStatus` 和 `RunSnapshot`。这一阶段回答两个问题：一次 Agent 执行需要哪些数据，以及它会经历哪些状态。

学习重点：区分 `run_id` 和 `thread_id`。前者标识一次执行，后者标识一段可延续的对话。

### 第二步：抽象 AgentRuntime

使用 `Protocol` 声明 RunManager 只需要 Agent 提供 `ainvoke()`。这样运行管理层不依赖某个具体模型，也不需要知道 Agent 内部如何创建。

学习重点：面向最小接口编程，以及如何用假 Agent 替换真实 Agent。

### 第三步：实现 RunManager

先登记 `queued` 状态，再通过 `asyncio.create_task()` 启动后台执行。后台任务负责更新 `running`、`completed` 或 `failed`。

学习重点：HTTP 请求生命周期与后台任务生命周期不是一回事；共享内存状态需要通过锁保护。

### 第四步：接入 create_agent() Agent

RunManager 调用 Agent 的公开 `ainvoke()`，传入消息、checkpoint 的 `thread_id` 配置以及业务 Context。这里不操作 LangGraph 内部节点。

学习重点：复用上一阶段的 thread/checkpoint 能力，而不是在 HTTP 层重新实现对话历史。

### 第五步：添加 FastAPI 路由

创建接口只负责登记 Run 并返回 HTTP 202；查询接口只读取快照。路由不直接访问 `_runs`，所有业务操作都经过 RunManager。

学习重点：App 是协议适配层，Harness 是可复用业务层。

### 第六步：组装应用与关闭清理

`create_app()` 注入 RunManager、注册路由，并在 FastAPI lifespan 结束时调用 `manager.aclose()`。

学习重点：后台任务也属于应用资源，服务关闭时必须清理。

### 第七步：验证三条核心路径

分别验证成功 Run、失败 Run 和未知 Run。测试使用假 Agent，不依赖真实模型和外部网络。

完成这七步后，数据流应当十分明确：

```text
请求 → 路由 → RunManager 登记 → 后台 ainvoke
  ↑                                  │
  └──────── 查询 RunSnapshot ←───────┘
```

## 2. 整体结构

```text
POST /api/threads/{thread_id}/runs
              │
              ▼
        FastAPI 路由
              │ 创建 Run
              ▼
         RunManager
          │       │
   立即返回 ID    └── 后台调用 create_agent() 创建的 Agent
          │                         │
          ▼                         ▼
      HTTP 202             completed 或 failed

GET /api/runs/{run_id} ──→ 查询最新状态
```

## 3. Run 与 thread

- **thread**：一段连续对话的状态命名空间；
- **run**：对某个 thread 发起的一次 Agent 执行。

同一个 thread 可以先后产生多个 Run。Run 有唯一 `run_id`，同时记录它属于哪个 `thread_id`。

## 4. 生命周期

```text
queued → running → completed
                 └→ failed
```

- `queued`：已经登记，但后台任务还未开始；
- `running`：正在调用 Agent；
- `completed`：执行成功，`output` 保存最终回答；
- `failed`：执行失败，`error` 保存错误信息。

终态是 `completed` 或 `failed`。本阶段还没有取消状态，取消将在下一阶段加入。

## 5. RunManager

`RunManager` 位于 Harness 的 `runtime` 包，负责：

1. 创建 `run_id`；
2. 保存内存中的 Run 快照；
3. 使用 `asyncio.create_task()` 启动后台执行；
4. 更新 Run 状态；
5. 调用 Agent 的 `ainvoke()`；
6. 在应用关闭时清理后台任务。

它不依赖 FastAPI，因此未来还可以被命令行、IM 渠道或其他协议复用。

## 6. 为什么复制快照？

`get_run()` 和 `create_run()` 返回 `RunSnapshot` 的副本，而不是内部正在被修改的对象。这样调用方不能绕过 Manager 直接改变 Run 状态。

## 7. HTTP 路由

### 创建 Run

```http
POST /api/threads/thread-1/runs
Content-Type: application/json

{
  "message": "你好",
  "user_id": "user-1"
}
```

接口返回 HTTP `202 Accepted`。它表示请求已接受执行，不表示 Agent 已经完成。

响应示例：

```json
{
  "run_id": "...",
  "thread_id": "thread-1",
  "user_id": "user-1",
  "status": "queued",
  "output": null,
  "error": null
}
```

### 查询 Run

```http
GET /api/runs/{run_id}
```

客户端可以轮询这个接口，直到状态进入 `completed` 或 `failed`。

## 8. 分层边界

```text
app/routers/runs.py
    HTTP 参数、响应模型、状态码
               │
               ▼
harness/mini_deerflow/runtime/runs.py
    生命周期、后台任务、Agent 调用
```

Harness 不得导入 App 或 FastAPI。App 可以导入 Harness 并把它组装成 HTTP 服务。

## 9. 为什么使用 Agent.ainvoke？

RunManager 面向 `create_agent()` 返回对象的公开异步接口 `ainvoke()`，不读取或修改 LangGraph 内部节点。后续阶段也继续通过 LangChain Agent 的公开能力扩展。

## 10. 当前限制

这是单进程教学实现：

- Run 只保存在内存中；
- 进程重启后 Run 记录消失；
- 不支持多进程共享；
- 没有取消和流式事件；
- 没有数据库事务。

这些能力会在后续阶段逐步加入。

## 11. 运行测试

```powershell
backend\.venv\Scripts\python.exe -m pytest examples\mini-deerflow-teacher\tests\test_async_runs_api.py -v
```

测试覆盖成功、失败和 404 三条路径，不调用真实模型。

## 12. 阶段考试

### 概念题

1. 为什么创建 Run 使用 HTTP 202，而不是等待后返回 200？
2. 一个 thread 是否只能拥有一个 Run？
3. 为什么 `RunManager` 放在 Harness，而 HTTP 路由放在 App？
4. `completed` 与 `failed` 分别保存什么结果？

### 实操题

增加接口：

```http
GET /api/threads/{thread_id}/runs
```

要求：

1. `RunManager` 增加按 `thread_id` 查询的方法；
2. 按 `created_at` 从早到晚返回；
3. thread 没有 Run 时返回空列表；
4. 路由层返回 `list[RunResponse]`；
5. 不允许路由直接访问 `RunManager._runs`。

单元测试不是强制验收项，但核心代码应能实际运行。

## 13. 答案要点

1. 202 表示服务器已接受异步工作，最终结果尚未产生。
2. 一个 thread 可以拥有多个先后执行的 Run。
3. 生命周期可以被多种协议复用；HTTP 只是应用适配层。
4. 成功保存 `output`，失败保存 `error`。
