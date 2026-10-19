# 第三阶段：thread 与 checkpoint

## 1. 学习目标

第二阶段由 `create_agent()` 创建的 Agent 只能在一次 `invoke()` 中维护状态。第三阶段加入 checkpoint，使多次调用可以按 `thread_id` 恢复之前的消息。

完成本阶段后，你应该能够：

1. 区分图状态、checkpoint 和 thread；
2. 使用相同 `thread_id` 延续一段对话；
3. 解释不同 thread 为什么不会共享消息；
4. 读取某个 thread 的最新状态快照；
5. 理解内存 checkpointer 的适用范围。

## 2. 三个概念

### State

State 是一次图运行过程中各节点共同读写的数据。当前只有 `messages`。

### Checkpoint

Checkpoint 是图运行到某个时刻时保存的状态快照。编译图时传入 checkpointer，LangGraph 会在运行过程中自动保存状态。

### Thread

Thread 是一组 checkpoint 的命名空间。调用图时通过配置传入：

```python
{"configurable": {"thread_id": "thread-a"}}
```

相同 ID 会读取并继续已有状态；不同 ID 使用不同的状态历史。

## 3. 创建带 checkpoint 的图

```python
checkpointer = create_memory_checkpointer()
graph = build_agent_graph(
    model=model,
    tools=[add],
    checkpointer=checkpointer,
)
```

`build_agent_graph()` 内部继续使用 `create_agent()`，自身不负责决定存储类型，只把 checkpointer 交给 LangChain。这让 Agent 与存储实现保持分离。

## 4. 延续同一个 thread

第一次调用：

```python
config = thread_config("thread-a")
graph.invoke(
    {"messages": [HumanMessage(content="我喜欢红色")]},
    config=config,
)
```

第二次调用只提交新的用户消息：

```python
graph.invoke(
    {"messages": [HumanMessage(content="我喜欢什么颜色？")]},
    config=config,
)
```

LangGraph 会先恢复 `thread-a` 的旧状态，再由 `add_messages` 合并新消息。最终历史包含两轮对话。

## 5. thread 隔离

`thread-a` 和 `thread-b` 即使共用同一个图和 checkpointer，也会写入不同的 checkpoint 命名空间。

```text
checkpointer
├── thread-a → A 的消息历史
└── thread-b → B 的消息历史
```

因此 `thread_id` 不是普通展示字段，而是状态所有权边界的一部分。

## 6. 读取状态快照

```python
snapshot = graph.get_state(thread_config("thread-a"))
messages = snapshot.values["messages"]
```

`get_state()` 不会重新运行模型，只读取指定 thread 的最新 checkpoint。

## 7. 为什么先用 InMemorySaver？

`InMemorySaver` 适合教学和单进程测试：

- 配置简单；
- 没有数据库依赖；
- 方便观察 checkpoint 行为。

它不适合生产环境：进程退出后数据消失，多个进程也不能共享状态。SQLite 持久化会在后续阶段加入。

## 8. 为什么 thread_id 不能为空？

启用 checkpointer 后，每次运行必须能确定状态属于哪个 thread。空 ID 会造成含义模糊，因此 `thread_config()` 会先去除首尾空白，再拒绝空字符串。

## 9. 运行测试

```powershell
backend\.venv\Scripts\python.exe -m pytest examples\mini-deerflow-teacher\tests\test_thread_checkpoints.py -v
```

测试覆盖：

- 同一 thread 恢复历史；
- 不同 thread 相互隔离；
- 空 thread ID 被拒绝。

## 10. 阶段考试

### 概念题

1. State 和 checkpoint 有什么区别？
2. 为什么同一个 checkpointer 可以保存多个 thread？
3. 第二次调用为什么只需要传入新的 `HumanMessage`？
4. 为什么 `InMemorySaver` 不适合多进程生产环境？

### 实操题

在 `checkpoints` 包中实现：

```python
def read_thread_messages(graph, thread_id: str) -> list[AnyMessage]:
    ...
```

要求：

1. 复用 `thread_config()`；
2. 使用 `graph.get_state()`，不得调用模型；
3. 已存在 thread 时返回消息列表；
4. 不存在状态时返回空列表；
5. 返回新的列表，调用方修改它不能影响 checkpoint 中的状态。

## 11. 答案要点

1. State 是运行数据，checkpoint 是某一时刻保存的 State 快照。
2. `thread_id` 为 checkpoint 提供隔离的命名空间。
3. checkpointer 会恢复旧状态，reducer 再合并本次的新消息。
4. 内存数据随进程消失，且不能在多个进程之间共享。
