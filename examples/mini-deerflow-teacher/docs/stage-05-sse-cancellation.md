# 阶段 5：SSE 流式输出与 Run 取消

## 本阶段目标

上一阶段已经能创建 Run 和查询最终状态，但客户端只能轮询，看不到模型正在
生成的内容。本阶段要建立 DeerFlow 的核心流式链路：

```text
Agent.astream()
    ↓ 生产消息块
RunManager
    ↓ 发布事件
MemoryStreamBridge
    ↓ 每个客户端独立订阅
FastAPI StreamingResponse
    ↓ SSE
浏览器或命令行客户端
```

同时增加取消链路：HTTP 路由找到 RunManager 中的 `asyncio.Task`，调用
`task.cancel()`；后台执行协程捕获 `CancelledError`，把状态写成 `cancelled`，
发布最后一个状态事件并关闭事件流。

## 一、为什么需要 StreamBridge

不能让 SSE 路由直接调用 Agent。Agent 是后台 Run 的生产者，而 SSE 请求只是
消费者：客户端可能晚一点连接、断开连接，也可能同时有多个消费者。

`StreamBridge` 把两者解耦：

- RunManager 只负责发布事件，不关心有没有 HTTP 客户端。
- SSE 路由只负责订阅事件，不负责执行 Agent。
- 历史事件允许客户端在 Run 开始后再连接。
- 每个订阅者维护独立读取游标，共享同一份有界事件日志。

Teacher 的内存实现已经保留 DeerFlow 的核心粒度：事件保留上限、
`Last-Event-ID` 断线续传、`StreamGap`、心跳、结束哨兵和显式清理。生产版
还可以换成 Redis，以支持跨进程消费和更完整的持久化恢复。

## 二、为什么使用 Agent.astream()

`ainvoke()` 只能在 Agent 完全结束后返回最终 State；`astream()` 会在生成过程
中逐块返回结果。本阶段使用 `stream_mode="messages"`，每项形如：

```python
(message_chunk, metadata)
```

RunManager 把非空文本块发布为 `message` 事件，同时将文本累积起来。流结束后，
累积文本写入 `RunSnapshot.output`，因此 SSE 与普通 GET 查询使用的是同一次 Run。

## 三、SSE 帧格式

SSE 是持续存在的 HTTP 响应，每条事件由空行分隔：

```text
id: 1760000000000-2
event: message
data: {"content": "42"}

```

本阶段定义三类事件：

- `status`：`running`、`completed`、`failed` 或 `cancelled`。
- `message`：模型产生的一段文本。
- `end`：由内部结束哨兵转换而来，收到后 SSE 响应退出。
- `gap`：客户端需要的历史已被裁剪，应重新读取 Run 的持久化状态。
- `: heartbeat`：SSE 注释帧，用来维持空闲连接。

## 四、代码阅读顺序

1. `harness/mini_deerflow/streaming/base.py`
2. `harness/mini_deerflow/streaming/bridge.py`
3. `harness/mini_deerflow/runtime/runs.py`
4. `app/gateway/app.py`
5. `app/routers/runs.py`

请按“桥接器 → 运行管理 → 生命周期注入 → HTTP 适配”的顺序阅读。

## 五、本阶段作业

只修改 `examples/mini-deerflow-backend`，不要复制整份 teacher 文件。

1. 在 `streaming` 包实现 `StreamEvent` 和 `MemoryStreamBridge`。
2. 给 `RunStatus` 增加 `CANCELLED`。
3. 将 RunManager 的 Agent 调用从 `ainvoke()` 改为 `astream()`。
4. 将消息块发布给 StreamBridge，并继续保存最终 `output`。
5. 实现 `cancel_run()`，确保取消后状态为 `cancelled`。
6. 在 lifespan 创建一个 StreamBridge，并注入 RunManager。
7. 实现 SSE 路由和取消路由。

不要求写测试类。完成后可用浏览器、curl 或普通 Python request 脚本进行实际调用。

## 六、验收标准

- 创建 Run 仍然立即返回 202。
- SSE 能依次收到 `status`、若干 `message` 和 `end`。
- SSE 得到的文本拼接后与 GET 返回的 `output` 一致。
- 取消运行中的 Run 后，GET 返回 `cancelled`。
- SSE 客户端在成功、失败或取消后都会退出，不会永久等待。
- `harness` 仍然不导入 `app` 或 FastAPI。

## 思考题

1. 为什么不能只用一个共享 `asyncio.Queue` 服务所有 SSE 客户端？
2. 为什么 `publish_end()` 必须放在后台执行逻辑的 `finally` 中？
3. 客户端断开 SSE，为什么不应该自动取消 Agent Run？
4. `run_id` 和 `thread_id` 在流式执行中分别解决什么问题？
