# 智慧校园助手 (Smart Campus Assistant)

基于 LangChain 的智能校园助手系统，面向南方科技大学学生，提供任务规划、知识库问答、学习辅助、自动化脚本和选课推荐等功能。

## 功能

| 模块 | 功能 |
|------|------|
| **日程规划** | 通过对话管理日历日程，支持增删改查、冲突检测、从 Blackboard/CAS/ToDoist 导入日程、草稿/提交工作流 |
| **校园信息助手** | 基于 RAG（检索增强生成）的校园知识问答，覆盖学校政策、办事流程、学术信息等 |
| **学习助手** | 上传课件（PPT/Markdown），自动生成多风格总结（简洁/详细/提纲/思维导图）和测验题目（单选/填空/判断/简答），支持难度控制和自动批改 |
| **脚本自动化** | 通过对话创建、管理和执行 Python 脚本，在沙箱环境中安全运行，支持流式输出和包管理 |
| **选课推荐** | 基于已完成课程、培养方案和 LLM 推理，生成个性化的学期选课计划，含学分检查和毕业要求追踪 |

## 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | Python 3.12+, FastAPI, Uvicorn |
| AI Agent | LangChain (`create_agent`), OpenAI-compatible API |
| LLM 服务 | DashScope (Qwen)、DeepSeek、MiniMax、OpenAI（多 provider 自动切换） |
| 向量检索 | FAISS, MiniMax/DashScope Embeddings |
| 前端 | React 19, TypeScript, Vite, Tailwind CSS 4 |
| 数据模型 | Pydantic v2 |
| PDF 处理 | PyMuPDF |
| 文档解析 | python-pptx, mistletoe |

## 快速开始

### 前置要求

- Python 3.12+
- Node.js 24+
- 阿里云 DashScope API Key

### 1. 克隆并安装依赖

```bash
# 后端
cd backend
pip install -r requirements.txt
playwright install chromium   # 课程推荐模块需要

# 前端
cd ../frontend
npm install
```

### 2. 配置环境变量

复制 `backend/.env` 文件，至少配置一个 LLM Provider：

```bash
# 推荐：DashScope（阿里云）
DASHSCOPE_API_KEY=sk-xxx
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen-plus

# 或 OpenAI
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gpt-4o-mini
```

### 3. 构建知识库（可选）

```bash
cd backend
python -m src.ingestion.index_course_knowledge_base   # 课程推荐知识库
python -m src.ingestion.index_documents                # 校园信息知识库
```

### 4. 启动

在两个终端分别运行：

```bash
# 终端 1：后端 (http://localhost:8000)
cd backend
python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload

# 终端 2：前端 (http://localhost:5173)
cd frontend
npm run dev
```

前端开发服务器自动将 `/api` 请求代理到 `http://localhost:8000`。

也可通过 `start.sh` 一键启动（需先确保依赖已安装）。
## 效果预览

校园信息助手问答示例：

![alt text](<figure/校园信息助手问答示例.png>)

在“校园信息助手”模块中，用户输入问题（如“如何申请校内VPN？”、“南方科技大学有哪几个食堂？”），系统会基于知识库检索生成回答，并直观展示每条回答的置信度、引用来源列表。

回答信息来源展示示例：

![alt text](<figure/回答信息来源展示示例.png>)

点击引用来源即可查看对应文档的详细内容，方便用户快速验证信息出处。例如，当提问“计算机系的学生需要修读多少学分？”时，回答所引用的信息来源中，置信度排名第一的是计算机系的培养方案，用户可以据此直接核对学分要求的真实性。


## 项目结构

```
├── backend/                    # Python FastAPI 后端
│   ├── src/
│   │   ├── api/                # FastAPI 路由和服务端入口
│   │   │   ├── server.py       # 主服务器（lifespan 管理、Agent 初始化）
│   │   │   ├── document_qa_api.py
│   │   │   └── routes/
│   │   │       ├── calendar.py
│   │   │       ├── chat.py
│   │   │       ├── chat_sessions.py
│   │   │       ├── course_recommendation.py
│   │   │       ├── learning_assistant.py
│   │   │       └── script_automation.py
│   │   ├── agents/             # LangChain Agent 定义
│   │   │   ├── scheduler/          # 日程规划 Agent
│   │   │   ├── learning_assistant/ # 学习助手 Agent
│   │   │   └── script_automation/  # 脚本自动化 Agent
│   │   ├── tools/              # Agent 可调用的 @tool 函数
│   │   │   ├── operator_calendar/  # 日历操作（CRUD + 草稿管理）
│   │   │   ├── blackboard_calendar/
│   │   │   ├── cas_course/         # CAS 课程表
│   │   │   ├── convert_calendar/   # 校历转换
│   │   │   ├── todoist/
│   │   │   ├── skill_loader/
│   │   │   ├── script_automation/  # 脚本自动化工具
│   │   │   ├── shared_utils/
│   │   │   ├── estimate_duration/
│   │   │   └── ocr_calendar/
│   │   ├── rag_pipeline/       # 检索增强生成流水线
│   │   │   ├── llm_service.py
│   │   │   ├── embeddings.py
│   │   │   ├── vector_store.py
│   │   │   ├── search.py
│   │   │   ├── service.py
│   │   │   └── prompt.py
│   │   ├── services/           # 业务逻辑
│   │   │   ├── course_recommendation/ # 选课推荐引擎
│   │   │   ├── document_qa/
│   │   │   ├── init_calendar/
│   │   │   └── skill_register/
│   │   ├── ingestion/          # 数据索引构建脚本
│   │   ├── core/               # 全局状态管理
│   │   └── models/             # Pydantic 数据模型
│   ├── data/                   # 校园数据（课程安排、爬取数据）
│   ├── resources/              # 日历持久化、用户脚本、对话历史
│   └── storage/                # FAISS 索引、上传文件
│
├── frontend/                   # React + TypeScript 前端
│   ├── src/
│   │   ├── App.tsx             # 主应用（侧边栏 + 5 个标签页）
│   │   ├── api.ts              # 所有后端 API 调用封装
│   │   └── components/
│   │       ├── SchedulePlanner.tsx
│   │       ├── CampusAssistant.tsx
│   │       ├── LearningAssistant.tsx
│   │       ├── ScriptAutomation.tsx
│   │       ├── CourseRecommendation.tsx
│   │       ├── StatusBar.tsx
│   │       ├── PersonalPanel.tsx
│   │       └── ModernCalendar.tsx
│   └── vite.config.ts
│
└── start.sh                    # 一键启动脚本
```

## Agent 架构

系统基于 LangChain 的 Agent 模式，每个 Agent 有明确的职责和工具集：

### 日程规划 Agent
- **工具**：日历 CRUD、草稿管理、Blackboard/CAS/ToDoist 导入、技能加载
- **工作流**：对话 → 编辑草稿日历 → 提交/重置 → 持久化
- **特点**：支持 SSE 流式输出、对话历史摘要、日程冲突检测

### 学习助手 Agent
- **输入**：.pptx/.ppt/.md 文件
- **能力**：4 种总结风格 + 4 种题型 + 3 级难度 + 自动批改
- **工具**：`summarize_document`、`generate_questions`、`list_supported_formats`

### 脚本自动化 Agent
- **沙箱**：独立目录，隔离虚拟环境，限制危险操作
- **工具**：脚本 CRUD、文件操作、包管理、流式执行
- **安全**：拦截 `subprocess`、`eval`、`ctypes` 等敏感操作

### 选课推荐模块
- **数据源**：TIS 教务系统（课表、已修课程）、培养方案 PDF
- **流程**：数据采集 → 向量检索 → LLM 推理 → 学分核算 → 毕业要求检查
- **输出**：推荐课程列表 + 可推迟课程 + 毕业进度摘要

## API 概述

| 路径 | 说明 |
|------|------|
| `GET /api/health` | 健康检查 |
| `GET/POST/PUT/DELETE /api/calendar/*` | 日历 CRUD + 草稿管理 |
| `POST /api/chat` | 日程 Agent SSE 对话 |
| `POST /api/script-chat` | 脚本 Agent SSE 对话 |
| `GET/PUT /api/script-sandbox` | 沙箱目录管理 |
| `POST /api/learning-assistant/*` | 学习助手（上传 + SSE 对话 + 批改） |
| `POST /api/qa/*` | 校园信息 RAG 问答 |
| `GET/POST /api/course-recommendation/*` | 选课推荐（学期、课表、计划、解释） |

> 流式接口使用 Server-Sent Events (SSE)，支持 `event:` / `data:` 格式，事件类型包括 `thought`、`tool_call`、`tool_result`、`script_execution`、`script_output`、`final`、`error` 等。

## LLM 配置

系统支持多 Provider 自动切换，优先级：

1. **DashScope (Qwen)** — 默认主 LLM，支持多模型轮转和额度管理
2. **DeepSeek** — 第一备选
3. **MiniMax** — 第二备选（也用于 Embedding）
4. **OpenAI** — 最终备选，也可作为 fallback 客户端

配置方式见 `.env` 文件，核心参数：

| 变量 | 说明 |
|------|------|
| `DASHSCOPE_API_KEY` | DashScope API Key |
| `DASHSCOPE_CHAT_MODELS` | 模型列表（逗号分隔，自动轮转） |
| `DASHSCOPE_CHAT_BUDGETS` | 各模型额度（token 数） |
| `DASHSCOPE_QUOTA_RATIO` | 额度告警比例（默认 0.95） |
| `USE_LLM_FALLBACK` | 是否启用 OpenAI 备用 |
| `AGENT_SUMMARY_TRIGGER` | Agent 摘要触发消息数 |
| `AGENT_SUMMARY_KEEP` | 摘要保留消息数 |

## 开发

### 运行测试

```bash
cd backend
python -m pytest tests/ -v
```

### 添加技能

技能定义在 `backend/src/skills/` 目录，以 Markdown 文件形式，通过 `skill_loader` 工具动态加载。参见 CLAUDE.md 中的技能创建规范。

## 常见问题

**Q: 启动后端提示缺失模块**
```bash
pip install -r requirements.txt
```
如提示 `playwright` 缺失，还需运行 `playwright install chromium`。

**Q: LLM 调用失败**
检查 `.env` 中 API Key 是否正确，以及网络是否可以访问对应 Provider。

**Q: 前端无法连接后端**
确认后端已启动在 8000 端口，检查 `frontend/vite.config.ts` 中的代理配置。

**Q: 课程推荐没有数据**
需先运行 `python -m src.ingestion.index_course_knowledge_base` 构建知识库，并确保 `backend/data/tis_download/` 下有课表数据。
