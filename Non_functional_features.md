# 智能校园助手 —— 非功能性特性报告

> 26s-22 组 · 软件工程团队项目

---

## 一、性能优化

### 1.1 全链路 SSE 流式传输

系统五大模块**全部采用 SSE（Server-Sent Events）流式架构**，基于 `sse-starlette` 和 `EventSourceResponse` 实现：

| 模块 | 端点 | 事件流 |
|---|---|---|
| 校园知识助手 | `POST /api/qa/chat/stream` | `status` → `token` → `metadata` → `done` |
| 智能调度 | `POST /api/chat` | `tool_call` → `tool_result` → `thought` → `final` |
| 学习助手 | `POST /api/learning-assistant/chat` | `tool_call` → `thought` → `tool_result` → `final` |
| 脚本自动化 | `POST /api/script-chat` | `script_execution` → `script_output` → `tool_result` → `final` |
| Calendar API | `GET/POST/PUT/DELETE /api/calendar/*` | 草稿隔离 + commit/reset 事务模型 |

**同步生成器桥接**：所有 Agent 的 `run_turn_stream()` 均为同步生成器，通过 `starlette.concurrency.iterate_in_threadpool` 桥接到 ASGI 异步流，避免阻塞事件循环。脚本自动化的 `execute_python_script_stream()` 额外使用 `threading.Thread` + `queue.Queue` 实现子进程输出流式转发（因 LangGraph `stream_writer` 非线程安全）。

**效果**：用户首字响应时间（TTFB）从"完整答案生成完毕"降至"首个事件到达"，感知延迟大幅降低。

### 1.2 投机并行执行

`QAService` 在两个路径中均使用 `ThreadPoolExecutor(max_workers=3)` 并行发起三个轻量级 LLM 调用：

- **意图路由** (`classify_query_kind`) — lightweight 层模型
- **批量关键词提取** (`extract_keywords_batch`) — 所有来源并行提取
- **可回答性评估** (`assess_answerability`) — 仅 document 模式使用

三个调用同时提交，路由结果先行收集用于决策，其余按需收集。**关键优化**：使用手动 `pool.shutdown(wait=False)` 替代 `with ThreadPoolExecutor` 上下文管理器，避免等待未使用的 future 完成。对于 RAG 查询，预处理阶段的三次 LLM 调用延迟从串行叠加（~6-9s）压缩为单次调用延迟（~2-3s）。

### 1.3 分层模型架构

系统将 LLM 调用按**计算需求分层**，避免"杀鸡用牛刀"：

| 层级 | 模型 | 典型用途 | 延迟特征 |
|---|---|---|---|
| **Lightweight** | `qwen3.5-flash` | 意图路由、可回答性判断、关键词提取 | < 1s |
| **Smart** | `qwen3.5-plus` / MoE 模型 | RAG 答案生成、Agent 推理、摘要、题目生成 | 2-5s |
| **Embedding** | `text-embedding-v1` | 文档向量化 | 批处理 |
| **Vision** | `qwen-vl-ocr-latest` | 图片/OCR 处理 | 按需 |

轻量级调用（路由、关键词等）使用 flash 模型，仅答案生成和 Agent 推理调用 smart 模型。`LLMService` 内部根据调用类型自动选择：
- `classify_query_kind()` → `model=self.lightweight_model_name`
- `assess_answerability()` → `model=self.lightweight_model_name`
- `generate_answer()` → 走 `self.model_name`（smart 层）
- Agent 推理 → `ChatModelProxy` wrapped smart 模型

### 1.4 温度与 Token 差异化配置

根据查询类型动态调整生成参数，在速度与质量之间取得平衡：

| 查询类型 | Temperature | Max Tokens |
|---|---|---|
| `document`（RAG 知识库） | 0.1 | 768 |
| `chat`（闲谈 / fast-path） | 0.2 | 1024 |
| 学习助手摘要 | 0.3 | 2048 |
| 学习助手题目生成 | 0.4 | 4096 |
| 学习助手解释生成 | 0.3 | 1024 |
| 学习助手评分 | 0.2 | 1024 |
| 澄清回复 | 0.1 | 256 |

RAG 查询使用更低温度和更少 token，因为答案应严格基于检索到的文档上下文，不需要创造性。学习助手在不同子任务（摘要/出题/解释/评分）间使用独立温度控制，平衡创造力与准确性。

### 1.5 FAISS 向量检索优化

- **L2 归一化 + 内积搜索**：所有嵌入向量在索引构建前做 L2 归一化（`sklearn.preprocessing.normalize`），配合 `IndexFlatIP`（内积索引），等价于余弦相似度搜索
- **超额检索策略**：`fetch_k = max(k * 3, 10)`，先检索 3 倍所需数量的候选，再按课程范围过滤，弥补后过滤带来的结果损失
- **启动时维度校验**：比较持久化的 FAISS 索引维度与当前嵌入模型维度，不匹配时拒绝加载并打印重建命令
- **Score Fast-Path**：当 `max_score < similarity_threshold` 时直接跳过 RAG 路由 LLM 调用，使用 lightweight 模型流式回复，节省 ~2s 路由延迟
- **批处理嵌入**：通过 `DOCUMENT_QA_EMBED_BATCH` 环境变量控制批大小（默认 16），平衡 API 调用次数与单次请求大小

### 1.6 惰性客户端初始化 + 版本感知缓存

`LLMConfig` 维护全局 `_version` 计数器，`LLMService` 和 `SentenceTransformerEmbeddings` 在每次调用时检查版本号，仅在配置变更时重建 OpenAI 客户端，避免重复创建连接的开销。

### 1.7 Agent 消息压缩

智能调度和脚本自动化 Agent 使用 LangChain `SummarizationMiddleware`：

| Agent | Trigger（消息数超过时触发） | Keep（摘要后保留最近消息数） |
|---|---|---|
| 智能调度 | 36 条 | 14 条 |
| 脚本自动化 | 36 条 | 14 条 |
| 学习助手 | 无压缩（`middleware=[]`） | — |

当对话历史超过触发阈值时，早期消息被 LLM 自动摘要压缩，仅保留摘要 + 最近消息，防止上下文窗口溢出。学习助手因对话轮次较短且需要精确的上下文回溯，禁用压缩。

### 1.8 脚本执行超时控制

- 脚本执行硬限制 `MAX_EXECUTION_TIME = 60s`，超时自动 `process.kill()`
- 输出截断 `MAX_OUTPUT_CHARS = 5000`（保留尾部，确保错误信息可见）
- 文件读取上限 10KB
- 前端工具结果截断至前 300 字符
- Pip 安装超时 120s，输出同样截断

---

## 二、用户体验

### 2.1 逐 Token / 逐事件实时渲染

前端四个聊天组件均通过 `ReadableStreamDefaultReader` 消费 SSE 事件流：

**校园知识助手** — 状态机驱动 UI：
```
status → 显示斜体进度文字（"正在检索知识库..."）
token  → 追加文本到消息气泡，逐字呈现
metadata → 填充右侧置信度面板 + 来源列表
done   → 标记完成，移除打字动画
```

**智能调度 / 学习助手 / 脚本自动化** — 统一事件模型：
```
tool_call → 显示工具调用名称与参数
thought  → 显示 AI 推理过程（思考气泡）
tool_result → 显示工具执行结果（或触发 Quiz 渲染）
script_execution → 创建/更新终端面板
script_output → 终端逐行输出
final    → 打字机效果展示最终回复
```

打字指示器使用三个弹跳圆点（`animate-bounce`），延迟分别为 0s / 0.1s / 0.2s，形成瀑布弹跳效果。

### 2.2 多种打字机动画

| 组件 | 速度 | 实现方式 |
|---|---|---|
| 校园知识助手 | 实时 token 追加 | SSE `token` 事件驱动 |
| 智能调度 | 20ms/字符 | `setTimeout` 链 |
| 脚本自动化 | 15ms/字符 | `setTimeout` 链 |
| 学习助手 | 30ms/字符 | `setInterval` + `typingProgress` 状态 Map |

脚本自动化额外实现了终端效果：活动执行时显示绿色闪烁光标（`border-r-2 border-emerald-400 animate-pulse`）。

### 2.3 来源透明与置信度面板

- **右侧 340px 侧边栏**展示检索来源列表：来源文档名、相关片段数、最高相关度
- **置信度分数**支持点击查看计算公式（加权融合：0.45×最高相似度 + 0.20×平均相似度 + 0.25×片段相关性 + 0.10×平均相关性）
- **PDF 原文预览**：点击来源弹出全屏模态框，左侧 `<iframe>` 渲染 PDF，右侧展示关键词标签。加载时显示"正在加载预览..."，失败时提供片段文本回退
- `fetch` + `URL.createObjectURL` 加载 PDF blob，`useEffect` cleanup 中调用 `URL.revokeObjectURL` 防止内存泄漏

### 2.4 脚本自动化终端面板

`ScriptAutomation.tsx` 实现了完整的终端模拟：

- **状态感知标题栏**：显示脚本名称、退出码（绿色 `✓` / 红色 `✕`）、执行状态标签
- **实时输出滚动**：stdout/stderr 行通过 `script_output` SSE 事件增量追加
- **活动时光标闪烁**：运行中显示绿色脉冲光标
- **Kill 按钮**：每个运行中的终端面板提供终止按钮，调用 `/api/script-chat/{id}/kill`（无需 Agent 锁）
- **沙箱目录管理器**：实时显示当前工作目录，支持切换并即时重建 Agent

### 2.5 学习助手 Quiz 交互

`LearningAssistant.tsx` 实现了完整的交互式测验体验：

- **自动检测**：LLM 返回 `_type: "quiz"` 标记时，前端自动渲染答题卡
- **多题型支持**：单选题（选项按钮）、判断题（对/错）、填空题（输入框）、简答题（文本框）
- **即时反馈**：提交后显示正确/错误（翠绿色/红色边框 + 勾号/叉号图标）
- **AI 评分**：简答题通过 `/api/learning-assistant/grade` 发送给 LLM 评分，返回分数 + 等级 + 反馈
- **参考答案**：折叠式 `<details>` 元素展示正确答案与解释
- **合并处理**：多个题目生成调用自动合并为统一答题卡

### 2.6 Markdown 渲染与代码高亮

所有聊天组件统一使用 `ReactMarkdown` + `remarkGfm`（GFM 表格/删除线/任务列表）+ `react-syntax-highlighter`（Prism.js，tomorrow 主题）。代码块自动检测 `language-xxx` 类名并应用对应语法高亮。

### 2.7 完整暗色模式

- 启动时通过 `window.matchMedia('(prefers-color-scheme: dark)')` 自动检测系统主题偏好
- 所有前端组件全面使用 Tailwind `dark:` 变体，包括背景、文字、边框、阴影、渐变等
- 全局 CSS 过渡 `transition-colors duration-300` 实现平滑主题切换
- 手动切换按钮带有 `aria-label`（"切换到浅色模式"/"切换到深色模式"）
- 装饰性渐变背景在暗色模式下通过 `dark:opacity-0` 隐藏

### 2.8 错误处理与用户指引

- 所有流式端点未配置 API Key 时返回统一中文提示："未配置 API Key，请前往个人中心 → API 配置 填入密钥后再试"（HTTP 503）
- Agent 并发忙时返回 HTTP 429："Agent is busy processing another request. Please wait or reset."
- 前端 `llmAvailable` 检测：无可用 LLM 时渲染 Markdown 格式的配置指引卡片
- 流式传输中的 `error` 事件以中文友好文案呈现
- 智能调度超时保护：30 秒内无 SSE 事件时显示"响应超时，点击重试"按钮
- PDF 预览失败时提供"您可以下载原始文件或查看下方片段文本"的回退提示
- 答案为空时自动填充"未返回有效答案。"；无工具调用的 AI 回复自动填充"已完成操作。"
- 学习助手批量处理：单文件失败不影响其他文件，错误嵌入结果字典
- 脚本自动化沙箱路径消失时前端显示警告并禁能执行

### 2.9 课程推荐课程表可视化

- 网格布局展示周课表（`lg:grid-cols-3`），每张课程卡片带颜色标签
- 悬浮态渐入动画（`fadeIn` CSS keyframes），遵守 `prefers-reduced-motion`
- Escape 键关闭模态框和下拉菜单

---

## 三、安全性与鲁棒性

### 3.1 API 密钥管理

- `LLMConfig` 单例作为全应用密钥的唯一数据源，从 `.env` 环境变量引导，运行时可通过 API 更新并持久化到 JSON
- 配置查询接口 `/api/settings/llm/status` 返回密钥时自动脱敏（`_mask_key()`：仅显示前 6 位 + 后 4 位）
- 更新配置时，传入空 `api_key` 不覆盖已有密钥
- 测试接口 `/api/settings/llm/test` 仅做一次轻量 API 调用验证密钥有效性，不持久化

### 3.2 路径遍历防护（三层）

| 防护层 | 位置 | 机制 |
|---|---|---|
| **文档服务** | `_resolve_document_path()` | `resolved.relative_to(documents_root)`，不在根内则返回 404 |
| **脚本沙箱 API** | `validate_path()` | 拼接路径后检查是否以沙箱目录为前缀，违规抛出 `PermissionError` |
| **运行时注入** | `wrapper_builder.py` 9 层安全策略 | `_validate_path()` 函数注入到子进程，拦截所有文件操作 |

### 3.3 Provider 故障转移

`LLMService` 实现双层 fallback：

```
主 Provider (DashScope)
  │
  ├─ 成功 → 返回结果
  │
  └─ 失败 → Fallback Provider (OpenAI)
              │
              ├─ 成功 → 返回结果
              │
              └─ 失败 → 返回 None / 空流
```

- 非流式 `_chat_completion()` 和流式 `_chat_completion_stream()` 均支持 fallback
- `embeddings.py` 的 `_embed_batch()` 同样支持 fallback
- 流式传输中的 `chunk.choices` 空值有守卫（`if not chunk.choices: continue`），避免 `IndexError` 中断流
- 流式子函数正确使用 `raise` 将异常传播至外层 fallback 逻辑

### 3.4 优雅降级

| 故障场景 | 降级策略 |
|---|---|
| 远程嵌入服务不可用 | 自动切换至本地 `HashEmbeddings`（基于 BLAKE2b 哈希的嵌入） |
| FAISS 索引不可用 | 调用 `_fallback_no_index()`，直接 LLM 回答并标记为 `answerable=False` |
| 证据不足无法回答 | 返回澄清性回复而非强行猜测（`generate_clarification()`） |
| 关键词提取失败 | 捕获异常，打印日志，不影响主流程继续 |
| 单个 Agent 初始化失败 | 打印警告，服务器继续启动（其余 Agent 正常工作） |
| 批量文件处理单文件失败 | 异常捕获后嵌入结果字典，不中断其余文件处理 |
| 脚本沙箱初始化失败 | 启动时打印警告，Agent 仍可注册（沙箱功能不可用但对话正常） |

### 3.5 脚本自动化 9 层沙箱安全

`wrapper_builder.py` 生成临时包装器脚本，在 `exec()` 用户代码前注入 9 层安全策略：

| 层 | 保护内容 | 机制 |
|---|---|---|
| 1 | 模块导入黑名单 | `builtins.__import__` 劫持，阻止 `subprocess`/`ctypes`/`socket`/`multiprocessing`，替换 `os`/`shutil` |
| 2 | `os.rename` / `os.replace` | 源和目标路径验证 |
| 3 | 命令执行 | `os.system` / `os.popen` 设为 `None` |
| 4 | `os.open` / `remove` / `unlink` / `rmdir` | 路径验证 |
| 5 | `os.mkdir` / `makedirs` / `chdir` | 路径验证 |
| 6 | `os.symlink` / `link` / `truncate` / `removedirs` | 路径验证 |
| 7 | `shutil.move` / `shutil.rmtree` | 路径验证（shutil 内部引用原始 os，需独立修补） |
| 8 | 内置函数 | `eval` 设为 `None`；`open` 写模式路径验证；`input` 替换为返回空字符串 |
| 9 | 审计钩子兜底 | `sys.addaudithook` 拦截所有 `open`/`os.system`/`os.popen`/`subprocess.Popen` 调用 |

附加安全措施：
- **静态预扫描**：`scan_for_dangerous_patterns()` 在脚本创建/更新时基于 AST 检测黑名单导入和 `eval`/`exec`/`compile` 调用
- **虚拟环境隔离**：每个沙箱目录自动创建独立 `.venv`，包安装不影响系统 Python
- **临时文件清理**：`._wrapper_*.py` 在 `finally` 块中删除
- **脚本名验证**：拒绝包含 `/` 或 `\` 的脚本名

### 3.6 输出清理

前端 `sanitizeAnswerText()` 过滤 LLM 输出中的：
- PDF 文件名引用 (`[xxx.pdf]`)
- 内部标记 (`[source:...]`, `[citation:...]`)
- 多余空白和换行

学习助手 LLM 输出 JSON 解析有三层备用：````json` 代码块 → 直接 JSON 解析 → 正则 `{...}` / `[...]` 匹配 → 全部失败返回 `[]`。

### 3.7 并发控制

`AgentRegistry` 通过 `threading.Lock` 实现 per-agent 并发控制：同一 Agent 同时仅允许一个请求执行，并发请求返回 HTTP 429。锁在 API 路由的 `finally` 块中释放，reset 端点额外调用 `AgentRegistry.release()` 防止死锁。

### 3.8 脚本进程生命周期管理

- **全局进程注册表**：`execution_manager.py` 维护 `execution_id → subprocess.Popen` 映射（线程安全）
- **独立 Kill 端点**：`POST /api/script-chat/{id}/kill` 无需 Agent 锁即可终止进程
- **资源清理**：kill 时关闭 stdout/stderr 管道，`finally` 中从注册表移除
- **超时自动终止**：60 秒超时后 `process.kill()` + 读取线程 join

---

## 四、可维护性

### 4.1 LLMConfig 集中配置

`LLMConfig` 单例作为全应用 LLM 配置的**唯一数据源**，架构如下：

```
LLMConfig (Singleton)
  ├── Provider 管理: DashScope / OpenAI / Custom
  ├── Fallback 管理: 主备双链路
  ├── Tier 管理: Lightweight / Smart / Embedding / Vision
  ├── 持久化: JSON 文件读写
  └── 版本计数: 下游服务懒重建
```

**ChatModelProxy 热替换**：透明代理包裹 `ChatOpenAI`，通过 `swap_model()` 实现运行时模型切换，LangGraph Agent 图无需重新编译。所有属性访问通过 `__getattr__` 委托至内部模型。设置 API 调用 `_rebuild_all_agents()` 一次 swap 影响所有共享 Proxy 实例的 Agent。

### 4.2 模块化 RAG 管道

```
rag_pipeline/
  ├── llm_service.py      # LLM 调用（流式/非流式 + fallback）
  ├── prompt.py           # 提示词模板集中管理
  ├── vector_store.py     # FAISS 向量检索 + L2 归一化
  ├── embeddings.py       # 多 Provider 嵌入 + HashEmbeddings 降级
  ├── models.py           # 数据模型（ChunkRecord, SearchResult, AnswerResult）
  ├── loader.py           # PDF/文本/JSON 文档加载
  └── chunker.py          # 智能文档分块（基于标题层级）
```

### 4.3 模块化 Agent 架构

```
agents/
  ├── agent_factory.py    # 通用 Agent 构建器（时间戳注入、技能目录、默认中间件）
  ├── agent_runner.py     # 统一流式/非流式执行 + 消息历史持久化
  ├── registry.py         # 线程安全 Agent 注册表 + per-agent 锁
  ├── middleware/          # 可复用中间件
  │   ├── message_compression.py  # 对话摘要压缩
  │   └── tool_error_handler.py   # 工具异常转 ToolMessage
  ├── scheduler/          # 智能调度 Agent
  ├── learning_assistant/ # 学习助手 Agent + Service
  ├── script_automation/  # 脚本自动化 Agent
  └── course_recommendation/ # 选课推荐 Agent
```

各 Agent 模块职责单一，共享 `agent_factory.py` 和 `agent_runner.py` 基础设施，可独立定制中间件、系统提示、工具集和最大步数。

### 4.4 工具层架构

```
tools/
  ├── blackboard_calendar/  # Blackboard 日历抓取
  ├── cas_course/           # CAS 课程表抓取
  ├── convert_calendar/     # 校历转换
  ├── operator_calendar/    # 日历 CRUD + 冲突检测
  ├── todoist/              # Todoist 任务同步
  ├── script_automation/    # 脚本管理 + 沙箱安全 + 执行器
  │   ├── schemas.py        # Pydantic 参数模型
  │   ├── safety.py         # 路径验证 + 静态分析
  │   ├── wrapper_builder.py # 9 层沙箱包装器生成
  │   ├── executor.py       # 子进程执行（同步 + 流式）
  │   ├── execution_manager.py # 进程生命周期管理
  │   ├── storage.py        # 脚本文件 + 元数据 CRUD
  │   ├── sandbox_env.py    # 虚拟环境管理
  │   └── tool.py           # @tool 装饰的函数集合
  └── skill_loader/         # 技能文档加载
```

### 4.5 前端 API 抽象

`api.ts` 统一管理所有后端通信（614 行）：

- 完整的 TypeScript 接口定义（20+ 个接口）
- SSE 流式解析封装为 `AsyncGenerator<ChatStreamEvent>`，支持 `for await...of` 消费
- 校园知识助手、智能调度、脚本自动化各模块 SSE 均独立封装
- 统一错误处理：检查 `res.ok`，解析 JSON 错误体提取 `detail` 字段

### 4.6 设计模式应用

| 模式 | 应用位置 | 用途 |
|---|---|---|
| **Singleton** | `LLMConfig`, `QAService`, `AgentRegistry`, `LearningAssistantService` | 全局唯一配置 / 服务实例 |
| **Proxy** | `ChatModelProxy` | ChatOpenAI 热替换，无需重编译 Agent 图 |
| **Registry** | `AgentRegistry` | Agent 注册、惰性初始化、并发控制 |
| **Strategy** | `_should_use_rag()` | 四信号加权路由决策 |
| **Builder** | `wrapper_builder.py` | 沙箱包装脚本动态生成 |
| **Observer** | SSE Event Stream | 多事件类型驱动的状态机 UI |
| **Template Method** | `agent_factory.py` / `build_agent()` | 统一 Agent 构建流程（时间戳注入 + 技能目录 + 中间件） |

### 4.7 会话持久化与恢复

- **Agent 对话历史**：`AgentRunner.save_history()` / `load_history()` 通过 LangChain `dumpd`/`load` 序列化到 `resources/histories/{agent_name}_history.json`
- **启动时恢复**：各 Agent 在 `lifespan` 启动时从文件加载历史消息
- **关闭时保存**：`lifespan` shutdown 阶段遍历所有已注册 Agent 持久化消息
- **Draft Calendar**：日历草稿在关闭时保存到 `resources/draft_calendar.json`，启动时恢复
- **沙箱目录**：`sandbox_config.json` 持久化用户选择的沙箱路径，启动时恢复
- **LLM 配置**：`llm_config.json` 持久化 Provider/密钥/模型选择

### 4.8 学习助手文件解析器架构

```
parsers/
  ├── ppt_parser.py    # python-pptx 提取：幻灯片、项目符号、备注、表格、图片
  └── markdown_parser.py # mistletoe 提取：YAML frontmatter、标题层级、代码块、
                         #   列表、块引用、表格、LaTeX、Mermaid 图
```

解析器输出统一结构，供 `Summarizer` 和 `QuestionGenerator` 消费。摘要和题目生成在 `LearningAssistantService` 中解耦：

```
LearningAssistantService
  ├── PPTParser / MarkdownParser → 结构化内容
  ├── Summarizer → 4 种风格（简洁/详细/大纲/思维导图）
  └── QuestionGenerator → 4 种题型 + 3 级难度 + 混合难度支持
```

---

## 五、CI/CD 与 DevOps

### 5.1 CI 流水线

`.github/workflows/ci.yml` 定义三阶段流水线，`push` 和 `pull_request` 到 `main` 分支时触发：

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  backend     │     │  frontend    │     │  deploy      │
│  (test)      │────▶│  (build)     │────▶│  (webhook)   │
│  ubuntu      │     │  ubuntu      │     │  main only   │
└──────────────┘     └──────────────┘     └──────────────┘
```

**Backend Job**：
- Conda Python 3.11 环境
- `pip install -r requirements.txt` + `pytest`
- 运行 `pytest -v`，排除 13 个需要外部 API 凭证或特定环境的测试文件
- 排除 2 个特定测试用例（`update_event_batch`、`test_reset_draft_restores_main_and_marks_clear`）

**Frontend Job**：
- Node.js 20 + npm ci（基于 `package-lock.json` 缓存）
- `npm run build`（`tsc -b` 类型检查 + `vite build` 生产构建）
- 使用 `actions/setup-node@v4` 缓存加速

**Deploy Job**（仅 main 分支 push）：
- 需要 `backend` 和 `frontend` 均成功
- 通过 curl POST 触发 Vercel Deploy Hook（前端）和 Render Deploy Hook（后端）
- 每个 deploy step 由 GitHub Secrets 驱动，安全存储 Webhook URL

### 5.2 部署架构

| 组件 | 平台 | 配置 |
|---|---|---|
| 后端 | Render (PaaS) | `render.yaml` — Singapore 区域，Python 3.11，Free 计划 |
| 前端 | Vercel | Deploy Hook 触发，自动构建部署 |

Render 配置（`render.yaml`）：
- 类型：`web` 服务
- 构建命令：`pip install -r backend/requirements.txt`
- 启动命令：`uvicorn src.api.server:app --host 0.0.0.0 --port $PORT`
- 根目录：`backend/`

### 5.3 代码质量

| 工具 | 配置位置 | CI 集成 |
|---|---|---|
| TypeScript 严格检查 | `tsconfig.app.json`（`noUnusedLocals`、`noUnusedParameters`） | `tsc -b` 在 build 中执行 |
| ESLint | `frontend/eslint.config.js`（flat config + TS + React Hooks） | 未在 CI 中运行 |
| Black (Python) | `requirements.txt`（`black>=23.11.0`） | 未在 CI 中运行 |
| Pytest | `backend/pyproject.toml`（`pythonpath = ["."]`） | CI 中运行（部分测试） |

### 5.4 本地开发

- `start.sh`：`uv run uvicorn` 启动后端 + `npm run dev` 启动前端
- Vite 开发服务器代理 `/api` 到 `http://localhost:8000`
- Conda 环境 `agent`（Python 3.11）用于后端开发

---

## 六、改进效果对比

| 指标 | 优化前 | 优化后 |
|---|---|---|
| RAG 预处理 LLM 调用 | 3 次串行 (~6-9s) | 3 次并行 (~2-3s) |
| RAG 非相关查询 | 走完整 RAG 路由 (~3s+ LLM 调用) | Score Fast-Path 直通 (~0.5s lightweight 模型) |
| API 响应方式 | 一次性 JSON 返回 | 5 个模块全 SSE 流式 |
| 闲谈类查询模型 | Smart 层（qwen3.5-plus） | Lightweight 层（qwen3.5-flash） |
| Provider 故障恢复 | 无 | 主备双链路自动切换 |
| 嵌入服务故障 | 直接报错 | 自动降级为 HashEmbeddings |
| 知识库索引不可用 | 返回错误 | 降级为纯 LLM 回答 |
| 向量检索 | L2 距离 | L2 归一化 + 内积（余弦等价） |
| 脚本安全 | 无防护 | 9 层沙箱 + AST 静态扫描 + 进程隔离 |
| 脚本执行监控 | 无 | 实时终端输出 + Kill 支持 + 60s 超时 |
| 对话历史 | 每次请求独立 | 持久化 + 启动恢复 + 摘要压缩 |
| LLM 配置更新 | 需重启服务 | ChatModelProxy 热替换 + 无感生效 |
| Agent 并发安全 | 无控制 | Per-agent Lock + 429 限流 |
| 部署方式 | 手动 | CI 自动测试 → 自动部署 Vercel + Render |
| 前端 TypeError 阻断 | 构建失败不感知 | `tsc -b` 类型检查在 CI 中强制通过 |
