# 第一阶段：最小工具调用 Agent

## 1. 学习目标

完成本阶段后，你应该能够：

1. 解释普通聊天模型与 Agent 的区别。
2. 说清 `HumanMessage`、`AIMessage`、`ToolMessage` 的职责。
3. 读懂一次“模型请求工具、程序执行工具、模型生成最终答案”的循环。
4. 解释为什么工具必须显式注册，以及为什么循环必须有步数上限。
5. 使用假模型在没有 API Key 和网络的情况下测试 Agent。

本阶段刻意不使用 LangGraph。先看清最小循环，第二阶段再把它改写成显式状态图。

## 2. 本阶段交付物

| 文件 | 职责 |
| --- | --- |
| `harness/mini_deerflow/agents/lead_agent/agent.py` | Agent 循环、结果类型和失败类型 |
| `harness/mini_deerflow/tools/arithmetic.py` | 带参数 Schema 的 `add` 工具 |
| `tests/test_minimal_agent.py` | 直接回答、工具调用、错误和上限测试 |

## 3. Agent 到底增加了什么？

普通聊天调用只有一条路径：

```text
用户输入 → 模型 → 文本回答
```

本阶段 Agent 增加了一个受程序控制的循环：

```text
用户输入
   ↓ HumanMessage
模型 ──直接回答──→ 最终结果
   │
   └─请求 add(a=2, b=3)
             ↓
        程序查找并执行工具
             ↓ ToolMessage(content="5")
            模型
             ↓
        最终回答“2 + 3 = 5”
```

关键点：模型并没有直接执行 Python 函数。模型只生成一个结构化的“工具调用请求”；真正的权限检查、函数查找和执行都由我们的 Agent 代码负责。

## 4. 三种消息

### `HumanMessage`

保存用户原始请求。`run_agent()` 创建消息列表时，它永远是第一条消息。

### `AIMessage`

模型响应。它可能包含最终文本，也可能包含 `tool_calls`：

```python
AIMessage(
    content="",
    tool_calls=[
        {"name": "add", "args": {"a": 2, "b": 3}, "id": "call-1"}
    ],
)
```

`id` 用来把工具结果和模型发出的请求关联起来。

### `ToolMessage`

程序执行工具后创建的结果消息：

```python
ToolMessage(content="5", name="add", tool_call_id="call-1")
```

这条消息会随完整历史再次发送给模型，因此模型能依据结果组织最终答案。

## 5. 逐段阅读 `run_agent()`

### 5.1 建立工具白名单

```python
tools_by_name = {tool.name: tool for tool in tools}
```

模型只能调用调用方明确传入的工具。模型即使生成 `delete_everything`，只要它不在字典里，Agent 就抛出 `UnknownToolError`。

### 5.2 向真实模型声明工具 Schema

```python
bind_tools = getattr(model, "bind_tools", None)
runnable_model = bind_tools(list(tools)) if callable(bind_tools) else model
```

LangChain 的真实聊天模型通过 `bind_tools()` 获得工具名称、说明和参数 Schema。测试假模型只需实现 `invoke()`，因此测试完全离线。

### 5.3 运行受限循环

```python
for step in range(1, max_steps + 1):
    response = runnable_model.invoke(messages)
```

每次调用模型算一步。`max_steps` 防止模型不停调用工具造成死循环和无限费用。

### 5.4 区分最终答案与工具请求

没有 `tool_calls` 时，响应就是最终答案；否则逐个校验并执行工具，把每个结果追加为 `ToolMessage`。

### 5.5 返回完整轨迹

`AgentResult` 不仅返回 `output`，还返回 `messages` 和 `steps`。这让调用方能够调试、审计和测试 Agent 的决策过程。

## 6. 为什么先使用假模型？

真实模型的输出可能随时间变化，而且需要网络和费用。单元测试必须快速、确定、离线。

`ScriptedModel` 按顺序返回预先写好的 `AIMessage`，因此测试可以准确构造：

- 直接回答；
- 先调用工具再回答；
- 请求未知工具；
- 达到循环上限。

真实模型适合后续单独进行人工或 opt-in 集成测试，不能替代这些单元测试。

## 7. 运行与观察

在仓库根目录运行本阶段测试：

```powershell
backend\.venv\Scripts\python.exe -m pytest examples\mini-deerflow-teacher\tests\test_minimal_agent.py -v
```

运行全部测试：

```powershell
backend\.venv\Scripts\python.exe -m pytest examples\mini-deerflow-teacher\tests -q
```

重点阅读 `test_agent_executes_a_tool_and_returns_the_follow_up_answer`。它就是完整工具调用流程的可执行说明。

## 8. 常见误区

1. **把模型当作工具执行器**：模型只提出调用请求，程序才拥有执行权限。
2. **把工具结果直接返回给用户**：工具结果通常仍需交回模型，由模型结合上下文生成答案。
3. **允许任意工具名**：必须用显式注册表限制能力范围。
4. **没有循环上限**：模型可能重复调用工具，导致无法终止。
5. **用真实 API 写单元测试**：测试会变慢、不稳定并产生费用。

## 9. 阶段考试

总分 100 分，80 分及格。

### A. 概念题（每题 10 分，共 40 分）

1. 模型返回工具调用请求后，为什么不能直接认为工具已经执行？
2. `tool_call_id` 解决了什么问题？
3. 为什么 `harness` 不能导入 `app`？
4. 为什么单元测试使用 `ScriptedModel`，而不是直接调用 OpenAI 或 DeepSeek？

### B. 读码题（每题 10 分，共 30 分）

1. 当 `AIMessage.tool_calls` 为空时，`run_agent()` 走哪条分支？
2. 模型请求未注册工具时，代码在哪里阻止它？
3. `max_steps=1` 且第一次响应请求工具时，为什么最终会抛出 `AgentLoopLimitError`？

### C. 实操题（30 分）

新增一个 `multiply(a: int, b: int) -> int` 工具，并完成以下内容：

1. 在 `harness/mini_deerflow/tools/` 中实现工具。（10 分）
2. 从 `harness.tools` 导出工具。（5 分）
3. 新增测试，证明 Agent 能调用它并得到正确结果。（10 分）
4. 全部测试通过且代码格式正确。（5 分）

## 10. 自测答案要点

完成考试后再对照：

1. 工具调用只是模型生成的结构化意图，执行权仍在宿主程序。
2. `tool_call_id` 将某条工具结果关联到对应请求；并行调用时尤其重要。
3. 保持核心运行层可复用，避免基础能力依赖具体应用和 HTTP 组装层。
4. 假模型离线、确定、快速、免费，可以稳定覆盖罕见错误分支。
5. 无工具调用时返回模型文本和完整轨迹。
6. `tools_by_name.get()` 返回空时抛出 `UnknownToolError`。
7. 第一步执行工具后循环没有第二次模型调用机会，循环结束并触发上限错误。

实操题没有直接给出代码答案；请用现有 `add` 工具和对应测试作为参照独立完成。
