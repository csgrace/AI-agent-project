# 日程 Executor Agent 需求文档

## 1. 设计目标

构建一个支持多轮对话的通用日历 Agent，具备：

- CRUD（创建 / 查询 / 修改 / 删除）
- 外部数据获取（fetch）
- 日程规划（planning）

系统核心要求：
- 状态一致性（draft为唯一真相源）
- 上下文可控（避免token爆炸）

## 2. 核心设计理念

系统采用：plan注入 +  三层视图（3-layer View）+ Hybrid 控制流（软决策 + 硬约束）

## 3. 上下文系统

### 3.1 Context A：PLAN

由 LangChain Memory 管理：[user, assistant, user, assistant...]

作用：
- 处理用户语义连续性
- 支持指代（“那个”“改一下”）
- 确保executor在仅看plan的情况下达到和看对话历史一样的效果

### 3.2 Context B：状态投影（State Projection）

由系统动态构造（Middleware生成）：

来源：Agent State（结构化）

输出：system prompt

作用：

- 提供“世界状态”
- 支持推理与决策
- 驱动工具调用

### 3.3 最终输入结构

LLM Input = system（State Projection）+plan （不一定是按这个顺序，可能重排部分文本块）

---

## 4. Agent State（内部状态）

系统维护结构化状态（用AgentState，方便中间件捕获）：
```python
state = {
	draft: {...}, # 完整日历数据（唯一真相源）
	working_memory: {
		goal: "...",
		history: [...], # 记录模型action的内容和反馈，例如做了什么事，结果是什么。可以理解为精简版的trace_log
		todo list: [...], # 格式以markdown列表的形式呈现（带已完成标记）
	},
	current_query_view: ..., # 当前查询结果（局部）
	step_count: int,
	is_finished: bool
}
```

## 5. 三层视图设计（3-Layer View）

Dynamic prompt Middleware必须构造以下三层视图：

### 5.1 Layer 1：Draft View

作用：
- 提供全局日历结构（例如规划1星期内事件，此处显示的就是这星期内每个事件的摘要）
- 支持快速定位事件

约束：
- 必须包含 id
- 不允许完整 JSON，将其以简洁的列表形式返回（类似markdown源码那种）
- 必须压缩

### 5.2 Layer 2：Query View（局部放大）

作用：
- 提供当前关注点细节

约束：
- 小规模（≤5条）
- 每个事件列出全部字段信息
- 每轮覆盖
- 不持久化
- 头部显示query到了几条事件

### 5.3 Layer 3：Working Memory（推理上下文）

作用：
- 提供“因果信息”
- 替代传统trace

约束：
- 必须简洁
- 可被模型更新

## 6. Middleware 设计

### 6.1 输入

视中间件的类型而定，wrap类型为model request，node类型为state。

### 6.2 输出

prompt_messages

### 6.3 核心职责

1. 渲染 Draft View
2. 渲染 Query View（若存在）
3. 渲染 Working Memory
4. 控制 token 长度

### 6.4 Prompt 模板（示例）

#### Execution 模式：

You are a calendar agent  should follow the plan to execute calendar schedule.
=== PLAN ===
...
=== CURRENT DRAFT ===
...
=== FOCUSED VIEW ===
...
=== WORKING MEMORY ===

RULES:
- Use tools when needed
- Update state via tools only

## 7. LLM 输出结构

必须结构化：

```json
{
	"intent": "spec | query | create | update | delete | fetch | finish",
	"action_input": {...}, # 工具调用参数
	"memory_update": {
		"todo list": [...], # 全量更新(仅当intent为spec时才读取，目的为更新todo list)
		"history info": [...] # 增量更新，内容为当前这一条计划要干什么。
	}
}
```

## 8. 控制流（Controller Loop）

while not finished:
	middleware构造prompt
	LLM输出
	若是spec intent：
		更新state里的memory update及history info
	若是finished intent：
		退出agent并将最终结果返回planner
	若是其他intent：
		执行对应操作
		在history info中append工具执行结果（成功或异常）
	step count ++