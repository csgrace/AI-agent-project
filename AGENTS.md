# AGENTS.md

## 项目概述

这是一个基于 LangChain 的智能校园助手系统，旨在为学生提供任务规划、知识库问答、文档处理、自动化脚本和选课推荐等功能。

- **项目名称**：智能校园助手系统
- **技术栈**：Python + LangChain + React（前端）
- **核心框架**：LangChain 用于构建智能体工作流

## 项目结构

```
project/
├── backend/                             # 后端服务
│   ├── credentials/
│   │   ├── profile.json
│   │   └── todoist_credentials.json
│   ├── src/
│   │   ├── agents/                      # Agent 定义与运行层
│   │   │   ├── agent_factory.py         # 通用 Agent 工厂（build_agent）
│   │   │   ├── agent_runner.py          # 流式事件标准化与容错
│   │   │   ├── registry.py              # Agent 注册表（多实例管理）
│   │   │   ├── cli.py                   # 统一 CLI 启动器（菜单式选择 Agent）
│   │   │   ├── middleware/              # 共享中间件
│   │   │   │   ├── tool_error_handler.py # 工具异常转 ToolMessage
│   │   │   │   └── message_compression.py# 长对话摘要
│   │   │   ├── scheduler/               # 已有：日程调度 Agent
│   │   │   │   ├── agent.py             # SchedulerDemoAgent 类 + 系统提示词
│   │   │   │   ├── tools.py             # 日程 Agent 专属工具集
│   │   │   │   └── cli.py               # 日程 Agent CLI 会话
│   │   │   ├── debug/                   # (预留)
│   │   │   └── graph/                   # (预留)
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── global_state.py          # SKILL_REGISTRY, CALENDAR, DRAFT_CALENDAR, OBJECT_STORE
│   │   │   └── object_store.py
│   │   ├── models/
│   │   │   └── calendar/
│   │   │       ├── __init__.py
│   │   │       ├── calendar.py
│   │   │       ├── calendar_event.py
│   │   │       ├── draft_calendar.py
│   │   │       ├── enums.py
│   │   │       ├── extraction.py
│   │   │       ├── recurring_rules.py
│   │   │       └── simple_event.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── init_calendar/
│   │   │   │   ├── __init__.py
│   │   │   │   └── loader.py
│   │   │   ├── init_object_store/
│   │   │   │   ├── __init__.py
│   │   │   │   └── initializer.py
│   │   │   └── skill_register/
│   │   │       ├── __init__.py
│   │   │       └── register.py
│   │   ├── skills/                      # 当前仓库可为空；运行时可由 AGENT_SKILLS_DIR 指向外部目录
│   │   └── tools/
│   │       ├── blackboard_calendar/
│   │       ├── convert_calendar/
│   │       ├── estimate_duration/
│   │       ├── filter_event/
│   │       ├── object_store_reader/     # 按 key 读取 OBJECT_STORE（非默认工具链）
│   │       ├── ocr_calendar/
│   │       ├── operator_calendar/       # query/add/update/remove/clear/reset_draft
│   │       │   ├── tool.py
│   │       │   ├── schemas.py
│   │       │   └── utils.py
│   │       ├── shared_utils/
│   │       │   ├── llm_event_judge.py
│   │       │   └── memory_adapter.py    # 未完工，仅占位接口
│   │       ├── skill_loader/
│   │       └── todoist/
│   ├── tests/
│   │   ├── test_agent_factory.py
│   │   ├── test_agent_runner.py
│   │   ├── test_blackboard_calendar.py
│   │   ├── test_blackboard_utils.py
│   │   ├── test_calendar.py
│   │   ├── test_calendar_event.py
│   │   ├── test_estimate_duration.py
│   │   ├── test_filter_event.py
│   │   ├── test_init_object_store.py
│   │   ├── test_memory_adapter.py
│   │   ├── test_object_store.py
│   │   ├── test_object_store_reader_tool.py
│   │   ├── test_operator_calendar.py
│   │   ├── test_schedule_demo_agent.py
│   │   ├── test_skill_loader.py
│   │   ├── test_skill_register.py
│   │   ├── test_skill_state.py
│   │   └── test_todoist.py
│   └── requirements.txt
├── frontend/                            # 前端服务（React + Vite + TypeScript）
│   ├── public/                       # 静态资源
│   │   ├── favicon.svg
│   │   └── icons.svg
│   ├── src/                          # 前端源代码
│   │   ├── assets/                   # 图片等资源
│   │   │   ├── hero.png
│   │   │   ├── react.svg
│   │   │   └── vite.svg
│   │   ├── components/               # React 组件
│   │   │   └── StatusBar.tsx
│   │   ├── App.css
│   │   ├── App.tsx
│   │   ├── index.css
│   │   └── main.tsx
│   ├── .gitignore
│   ├── README.md
│   ├── eslint.config.js
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── tailwind.config.js
│   ├── tsconfig.app.json
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   └── vite.config.ts
├── .gitignore
├── AGENTS.md
├── HUMAN_PLAN.md
├── README.md
├── require.md
└── proposal-26s-22.md
```

## 常用命令

```bash
# 运行测试
cd backend
python -m pytest tests/ -v
```

## 项目特定规则

### 1. 技能（Skill）创建规范

#### 1.1 技能文件结构

技能以 `.md` 文件形式存放在 `backend/src/skills/{skill_name}/` 目录下：

```
skills/
└── {skill_name}/
    └── skill.md
```

#### 1.2 技能文件格式

技能文件必须包含 **YAML frontmatter**，格式如下：

```markdown
---
name: skill_name          # 技能唯一标识名
description: 技能描述      # 此处并非只是技能的简单概况，其更多需要包含模型何时调用此技能的提示
---

# 技能标题

## 技能描述

详细描述本技能的功能和用途。

### 所用工具

- tool_name: 工具描述
- another_tool: 另一个工具描述

## 技能步骤

用有序列表表述技能步骤
```

#### 1.3 技能注册与加载方式

**注册流程**：

1. **扫描**：`services/skill_register/register.py` 中的 `scan_skills()` 函数扫描 `skills/` 目录
2. **解析**：解析每个 `skill.md` 文件的 YAML frontmatter，提取 `name` 和 `description`
3. **注册**：将技能元数据存入 `core/global_state.py` 中的全局 `SKILL_REGISTRY` 字典

```python
# 注册表示例
SKILL_REGISTRY = {
    "fetch_calendar": {
        "path": ".../fetch_calendar/skill.md",
        "description": "获取校历并转换为事件列表"
    }
}
```

**加载方式**：

- 让模型使用 `tools/skill_loader/tool.py` 中的 `load_skill(skill_name)` 工具加载技能内容

**刷新机制**：

- 调用 `refresh_skills(skills_dir)` 会重新扫描并整体刷新注册表
- 当前实现为“全量重建注册表”，不依赖 `last_modified` 时间戳

### 2. 工具（Tool）创建规范

#### 2.1 工具目录结构

每个工具存放在独立的目录中：

```
tools/
└── {tool_name}/
    ├── __init__.py       # 包初始化（可选）
    ├── tool.py           # 工具主文件（必须）
    ├── utils.py          # 辅助函数（可选）
    └── test_tool.py      # 测试文件（可选）
```

#### 2.2 工具实现规范

工具使用 **LangChain 的 `@tool` 装饰器** 定义：

```python
from langchain.tools import tool
from typing import List, Optional

@tool
def tool_name(param: str) -> str:
    """工具的详细描述。
    
    描述工具的功能、参数含义、返回值、异常情况和示例。
    
    Args:
        param: 参数说明
        
    Returns:
        返回值说明
        
    Raises:
        ValueError: 异常情况说明
        
    Example:
        >>> result = tool_name("example")
        >>> print(result)
    """
    # 实现逻辑
    return result
```

#### 2.3 工具开发要点

1. **必须使用 `@tool` 装饰器**：使函数可被 LangChain Agent 识别和调用
2. **简明恰当的方法名称**：工具方法名应简洁、描述性，与工具功能相关，因为这即是模型看见并调用的名称
3. **详细的 docstring**：Agent 根据 docstring 理解工具用途，必须包含：
   - 功能描述
   - Args：参数说明
   - Returns：返回值说明
   - Raises：可能的异常
   - Example：使用示例
4. **类型注解**：所有参数和返回值必须添加类型注解
5. **错误处理**：工具内部应捕获异常并抛出清晰的错误信息
6. **工具链组合**：复杂任务可拆分为多个工具，通过技能（skill.md）描述组合方式
7. **大型数据对象传递**：`object_store` 是可选机制。当前默认“轻量模式”下，工具优先返回可直接消费的摘要与必要字段（例如 query overflow 返回提示信息），只有在确有跨工具共享大对象需求时再使用 `OBJECT_STORE`。
8. **Calendar Event 特别说明**：当前核心链路是“主日历 -> draft 编辑 -> 审批后 sync_draft 回写主日历”。要保证事件原位覆盖，关键是保持事件 `id` 不变。因此在开发工具时，除 fetch/创建新事件场景外，优先在原对象上更新字段，避免无必要地新建事件对象。

### 3. 智能体（Agent）创建规范

#### 3.1 你只需要编写的部分

每个新 Agent 是一个独立的子包 `agents/{your_agent}/`，至少包含 `__init__.py` 和 `agent.py`（Agent 类 + 专属 system prompt）。推荐同时提供 `tools.py`（该 Agent 专用的 @tool 函数列表）。

可选文件：`cli.py`（该 Agent 的 CLI 交互循环，供统一 CLI 菜单调用）。

> **注**：API 路由和 Pydantic 模型可按需放置。调度助手将其放在 `api/routes/` 和 `api/schemas.py`（历史原因）。新 Agent 也可选择放在自己目录下的 `api.py` / `models.py` 中实现自包含，这不是强制的。

#### 3.2 共享基础设施（直接调用即可）

- **`build_agent(model, *, tools, system_prompt, skill_registry=None, middleware=None)`**（`agent_factory.py`）：拼装 system prompt（追加时间戳 + 技能目录）、组装中间件管道、调用 LangChain `create_agent()` 返回编译好的 Agent。`system_prompt` 是必填参数，无默认值。`middleware` 不传时使用默认列表（`SummarizationMiddleware` + `handle_tool_error`）。
- **`default_middleware(model)`**（`agent_factory.py`）：返回默认中间件列表，可在其基础上增减。
- **`AgentRunner(compiled_agent)`**（`agent_runner.py`）：管理 `self.messages` 对话历史，调用 `compiled_agent.stream()` 并将 LangChain 原始 chunk 标准化为 `tool_call` / `tool_result` / `thought` / `final` / `error` 事件，含异常兜底和空回复补全。
- **`AgentRegistry`**（`registry.py`）：多 Agent 实例注册与按名查找，每 Agent 独立互斥锁，支持 Eager（`register`）和 Lazy（`register_factory`）两种策略。

#### 3.3 添加新 Agent 的步骤

1. 创建 `agents/{your_agent}/` 目录，编写 `agent.py`（Agent 类 + system prompt）、`tools.py`（@tool 函数）
2. 在 `api/server.py` 的 lifespan 中注册：`AgentRegistry.register("name", YourAgent(llm))`，并 `app.include_router(your_router)`
3. 在 `agents/cli.py` 的 `_show_menu()` 和 `main()` 中加一个分支（可选）
4. 前端加对应的 Tab 和 API 调用（可选）

#### 3.4 中间件定制

`build_agent(..., middleware=...)` 接受中间件列表。不传时使用默认（摘要 + 错误恢复）。可在 `default_middleware(model)` 基础上增减，或传 `[]` 完全禁用。

#### 3.5 注册生命周期

- **Eager**：`AgentRegistry.register("name", instance)` — 启动时创建常驻内存，适合核心 Agent
- **Lazy**：`AgentRegistry.register_factory("name", factory_fn)` — 首次 `get("name")` 时创建，适合非核心 Agent

### 4. 当前运行时约定（2026-04）

1. **审批触发归 CLI**：在 `scheduler/cli.py` 中以 `draft.dirty != DirtyType.CLEAR` 判断是否需要审批；`SchedulerDemoAgent` 仅负责会话执行与流式事件，不负责审批门禁判断。
2. **提交与保存归 CLI**：用户确认后由 CLI 执行 `calendar.sync_draft(...)`、将 `draft.dirty` 置回 `CLEAR`，并持久化主日历。
3. **拒绝提交时回滚**：CLI 调用 `reset_draft_from_main()` 将 draft 还原为主日历镜像。
4. **工具异常可恢复**：通过 `tool_error_handler` 中间件将工具异常转为 `ToolMessage` 返回模型，避免因工具异常直接中断会话。

## 注意事项
