# 第二阶段：create_agent 与自定义状态

## 1. 学习目标

第一阶段手写循环帮助我们理解了模型、工具和消息之间的关系。从第二阶段开始，使用 LangChain 的 `create_agent()` 创建标准 Agent，不再自行编写 `StateGraph` 节点和边。

完成本阶段后，你应该能够：

1. 使用 `create_agent()` 创建工具调用 Agent；
2. 理解 `AgentState` 已经提供的消息状态；
3. 通过继承 `AgentState` 增加自定义字段；
4. 使用 `state_schema` 和 `context_schema` 配置 Agent；
5. 区分 State 与 Context。

## 2. 为什么使用 create_agent？

`create_agent()` 已经封装了通用 Agent 循环：

```text
用户消息 → 模型
           ├─ 最终回答 → 结束
           └─ 工具调用 → 执行工具 → 回到模型
```

它负责处理消息状态、工具路由和循环控制。教学项目只扩展业务真正需要的状态和上下文，不重复实现框架已有能力。

## 3. ThreadState

```python
class ThreadState(AgentState):
    model_calls: Annotated[int, operator.add]
```

`ThreadState` 继承 `AgentState`，因此自动拥有 `messages` 字段及对应的消息 reducer。

`model_calls` 展示了添加自定义状态字段的方式。`operator.add` 是 reducer，多个状态更新中的整数会累加，而不是相互覆盖。

当前阶段只声明这个字段，不强制实现计数逻辑。后续需要统计模型调用时，可以由中间件更新它。

## 4. RequestContext

```python
class RequestContext(TypedDict):
    thread_id: str
    user_id: str
```

Context 是一次调用期间可读取、但不作为对话状态演进的数据。用户身份等请求信息适合放在 Context 中。

需要跨节点和跨 checkpoint 保存的数据放入 State；只描述本次请求环境的数据放入 Context。

## 5. 创建 Agent

```python
agent = create_agent(
    model=model,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
    state_schema=ThreadState,
    context_schema=RequestContext,
    checkpointer=checkpointer,
)
```

各参数职责：

- `model`：聊天模型；
- `tools`：允许模型调用的工具白名单；
- `system_prompt`：Agent 的基础行为说明；
- `state_schema`：可持久化、可演进的图状态；
- `context_schema`：本次请求的上下文结构；
- `checkpointer`：可选的 thread 状态保存器。

## 6. 调用 Agent

```python
result = agent.invoke(
    {"messages": [HumanMessage(content="计算 7 + 5")]},
    context={"thread_id": "thread-1", "user_id": "user-1"},
)
```

返回结果仍然是状态字典，其中的 `messages` 包含用户消息、模型工具请求、工具结果和最终回答。

## 7. 与第一阶段对照

| 第一阶段 | 第二阶段 |
| --- | --- |
| 手写 Agent 循环 | `create_agent()` |
| 手工维护消息列表 | 继承 `AgentState` |
| 手工查找并执行工具 | LangChain Agent 自动处理 |
| 没有请求 Context | `context_schema` 声明结构 |
| 返回自定义 `AgentResult` | 返回 Agent State |

第一阶段用于理解原理，第二阶段开始采用框架的标准入口。

## 8. 运行示例测试

```powershell
backend\.venv\Scripts\python.exe -m pytest examples\mini-deerflow-teacher\tests\test_create_agent.py -v
```

测试内容验证 `create_agent()` 的标准工具调用行为。

## 9. 阶段考试

### 概念题

1. `create_agent()` 替我们处理了哪些通用工作？
2. `ThreadState` 为什么继承 `AgentState`？
3. State 与 Context 的主要区别是什么？
4. reducer 解决了什么问题？

### 实操题

在自己的项目中：

1. 定义继承 `AgentState` 的 `ThreadState`；
2. 定义包含 `thread_id` 和 `user_id` 的 `RequestContext`；
3. 使用 `create_agent()` 并传入两个 Schema；
4. 使用已有工具完成一次工具调用。

不需要手写 `StateGraph`、节点或条件边。

## 10. 答案要点

1. `create_agent()` 处理模型调用、工具路由、消息状态和循环控制。
2. 复用标准消息字段与 reducer，避免重新定义框架已有状态。
3. State 会随 Agent 演进并可进入 checkpoint；Context 描述本次调用环境。
4. reducer 定义多个状态更新如何合并，避免简单覆盖。
