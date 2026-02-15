# VibeWorker 开发需求文档 (PRD)
## 一、项目介绍
### 1. 功能与目标定位
**VibeWorker** 是一个基于 **Python** 构建的、轻量级且高度透明的 AI 数字员工 Agent 系统。
本项目不追求构建庞大的 SaaS 平台，而是致力于打造一个**运行在本地的、拥有“真实记忆”的智能数字员工**。它可以帮助用户处理各类任务，包括但不限于信息检索、数据处理、代码执行、文件管理等。其核心差异化定位在于：

+ **文件即记忆 (File-first Memory)**：摒弃不透明的向量数据库，回归最原始、最通用的 Markdown/JSON 文件系统。用户的每一次对话、Agent 的每一次反思，都以人类可读的文件形式存在。
+ **技能即插件 (Skills as Plugins)**：遵循 Anthropic 的 Agent Skills 范式，通过文件夹结构管理能力，实现“拖入即用”的技能扩展。
+ **透明可控**：所有的 System Prompt 拼接逻辑、工具调用过程、记忆读写操作对开发者完全透明，拒绝“黑盒”Agent。

### 2. 项目核心技术架构
本项目要求完全采用 **前后端分离** 架构，后端作为纯 API 服务运行。

+ **后端语言**：Python 3.10+ (强制使用 Type Hinting)。
+ **Web 框架**：**FastAPI** (提供 RESTful 接口，支持异步处理)。
+ **Agent 编排引擎**：**LangChain 1.x (Stable Release)**。
    - **核心 API**：必须使用 `**create_agent**` API (`from langchain.agents import create_agent`)。这是 LangChain 1.0 版本发布的最新标准 API，用于构建基于 Graph 运行时的 Agent。
    - **核心说明**：严禁使用旧版的 `AgentExecutor` 或早期的 `create_react_agent`（旧链式结构）。`create_agent` 底层虽然基于 LangGraph 运行时，但提供了更简洁的标准化接口，本项目应紧跟这一最新范式。
+ **RAG 检索引擎**：**LlamaIndex (LlamaIndex Core)**。
    - 用于处理非结构化文档的混合检索（Hybrid Search），作为 Agent 的知识外挂。
+ **模型接口**：兼容 OpenAI API 格式（支持 OpenRouter, Zenmux 等聚合模型平台，并且也支持用户自己配置API地址和Key）。
+ **数据存储**：本地文件系统 (Local File System) 为主，不引入 MySQL/Redis 等重型依赖。

## 二、内置工具
VibeWorker 在启动时，除了加载用户自定义的 Skills 外，必须内置以下 5 个核心基础工具（Core Tools）。根据“优先使用 LangChain 原生工具”的原则，技术选型更新如下：

### 1. 命令行操作工具 (Command Line Interface)
+ **功能描述**：允许 Agent 在受限的安全环境下执行 Shell 命令。
+ **实现逻辑**：
    - **直接使用 LangChain 内置工具**：`langchain_community.tools.ShellTool`。
    - **配置要求**：
        * 初始化时需配置 `root_dir` 限制操作范围（沙箱化），防止 Agent 修改系统关键文件。
        * 需预置黑名单拦截高危指令（如 `rm -rf /`）。
+ **工具名称**：`terminal`。

### 2. Python 代码解释器 (Python REPL)
+ **功能描述**：赋予 Agent 逻辑计算、数据处理和脚本执行的能力。
+ **实现逻辑**：
    - **直接使用 LangChain 内置工具**：`langchain_experimental.tools.PythonREPLTool`。
    - **配置要求**：
        * 该工具会自动创建一个临时的 Python 交互环境。
        * **注意**：由于 `PythonREPLTool` 位于 `experimental` 包中，需确保依赖项安装正确。
+ **工具名称**：`python_repl`。

### 3. Fetch 网络信息获取
+ **功能描述**：用于获取指定 URL 的网页内容，Agent 联网的核心。
+ **实现逻辑**：
    - **直接使用 LangChain 内置工具**：`langchain_community.tools.RequestsGetTool`。
    - **增强配置 (Wrapper)**：
        * 原生 `RequestsGetTool` 返回的是原始 HTML，Token 消耗巨大。
        * **必须封装**：建议继承该类或创建一个 Wrapper，在获取内容后使用 `BeautifulSoup` 或 `html2text` 库清洗数据，仅返回 Markdown 或纯文本内容。
+ **工具名称**：`fetch_url`。

### 4. 文件读取工具 (File Reader)
+ **功能描述**：用于精准读取本地指定文件的内容。这是 Agent Skills 机制的核心依赖，用于读取 `SKILL.md` 的详细说明。
+ **实现逻辑**：
    - **直接使用 LangChain 内置工具**：`langchain_community.tools.file_management.ReadFileTool`。
    - **配置要求**：
        * 必须设置 `root_dir` 为项目根目录，严禁 Agent 读取项目以外的系统文件。
+ **工具名称**：`read_file`。

### 5. RAG 检索工具 (Hybrid Retrieval)
+ **功能描述**：当用户询问具体的知识库内容（非对话历史）时，Agent 可调用此工具进行深度检索。
+ **技术选型**：**LlamaIndex**。
+ **实现逻辑**：
    - **索引构建**：支持扫描指定目录（如 `knowledge/`）下的 PDF/MD/TXT 文件，构建本地索引。
    - **混合检索**：必须实现 **Hybrid Search**（关键词检索 BM25 + 向量检索 Vector Search）。
    - **持久化**：索引文件需持久化存储在本地（`storage/`）。
+ **工具名称**：`search_knowledge_base`。

## 三、mini OpenClaw 的 Agent Skills 系统
### 1. Agent Skills 基础功能介绍
mini OpenClaw 的 Agent Skills 遵循 **"Instruction-following" (指令遵循)** 范式，而非传统的 "Function-calling" (函数调用) 范式。这意味着 Skills 本质上是**教会 Agent 如何使用基础工具（如 Python/Terminal）去完成任务的说明书**，而不是预先写好的 Python 函数。

Agent Skills 以文件夹形式存在于 `backend/skills/` 目录下。


### 2. Agent Skills 载入与执行流程
#### 2.1 Agent Skills 读取流程 (Bootstrap)
在 Agent 启动或会话开始时，系统扫描 `skills` 文件夹，读取每个 `SKILL.md` 的元数据（Frontmatter），并将其汇总生成 `SKILLS_SNAPSHOT.md`。

`**SKILLS_SNAPSHOT.md**`** 示例：**

```plain
<available_skills>  
  <skill>  
    <name>get_weather</name>  
    <description>获取指定城市的实时天气信息</description>  
    <location>./backend/skills/get_weather/SKILL.md</location> 
  </skill>
</available_skills>
```

_注意：_`_location_`_ 使用相对路径。_

#### 2.2 Agent Skills 调用流程 (Execution)
这是本系统最独特的地方：

1. **感知**：Agent 在 System Prompt 中看到 `available_skills` 列表。
2. **决策**：当用户请求“查询北京天气”时，Agent 发现 `get_weather` 技能匹配。
3. **行动 (Tool Call)**：Agent **不调用**`get_weather()` 函数（因为它不存在），而是调用 `**read_file(path="./backend/skills/get_weather/SKILL.md")**`。
4. **学习与执行**：Agent 读取 Markdown 内容，理解操作步骤（例如：“使用 fetch_url 访问某天气 API” 或 “使用 python_repl 运行以下代码”），然后**动态调用 Core Tools** (Terminal/Python) 来完成任务。

### 3. Agent Skills 的一些特性
#### 3.1 兼容Claude Code
本工程的Agent Skills 需要能兼容本地的Claude Code插件（即如果本地安装了ClaudeCode，同样允许用户可以使用到安装在ClaudeCode里的Skill，如果用户没有安装Claude Code则无影响）

#### 3.2 技能商店 (Skills Store) ✅ 已实现
提供一个技能商店，集成 [skills.sh](https://skills.sh/) 生态系统：

**功能特性：**
- 浏览 500+ 社区技能
- 按分类筛选（工具、数据、网络、自动化、集成等）
- 关键词搜索技能
- 一键安装到本地 `skills/` 目录
- 分页展示（每页 12 个技能）
- 查看技能详情和 SKILL.md 内容

**技术实现：**
- 后端 `backend/store/` 模块负责与 skills.sh 交互
- 从 skills.sh 页面提取技能数据（通过正则匹配嵌入的 JSON）
- 从 GitHub 原始内容获取 SKILL.md 文件
- 前端 `frontend/src/components/store/` 提供商店 UI

**CLI 工具：**
```bash
# Linux/macOS
./scripts/skills.sh list              # 列出本地技能
./scripts/skills.sh search <query>    # 搜索远程技能
./scripts/skills.sh install <name>    # 安装技能

# Windows
scripts\skills.bat list
scripts\skills.bat search <query>
scripts\skills.bat install <name>
```

#### 3.3 技能翻译功能 ✅ 已实现
编辑器支持一键将 SKILL.md 文件翻译为中文：
- 点击翻译按钮，调用 LLM 进行智能翻译
- 仅翻译描述性内容，保留代码块、URL、变量名等
- 翻译过程中显示加载动画
- 支持撤销更改恢复原文


## 四、mini OpenClaw 对话记忆管理系统设计
### 1. 本地优先原则
所有记忆文件（Markdown/JSON）均存储在本地文件系统，确保完全的数据主权和可解释性。

### 2. 系统提示词 (System Prompt) 构成
System Prompt 由以下 6 部分动态拼接而成（按顺序）：

1. `SKILLS_SNAPSHOT.md` (能力列表)
2. `SOUL.md` (核心设定)
3. `IDENTITY.md` (自我认知)
4. `USER.md` (用户画像)
5. `AGENTS.md` (行为准则 & **记忆操作指南**)
6. `MEMORY.md` (长期记忆)

**截断策略**：如果拼接后 Token 超出模型限制（或单文件超 20k 字符），需对超长部分进行截断并在末尾添加 `...[truncated]` 标识。

### 3. AGENTS.md 的默认配置 (核心修正)
由于 Agent 默认并不知道它是通过“阅读文件”来学习技能的，因此必须在初始化时生成一个包含明确指令的 `AGENTS.md`。

+ **必须包含的元指令 (Meta-Instructions)**：

```plain
# 操作指南

## 技能调用协议 (SKILL PROTOCOL)
你拥有一个技能列表 (SKILLS_SNAPSHOT)，其中列出了你可以使用的能力及其定义文件的位置。
**当你要使用某个技能时，必须严格遵守以下步骤：**
1. 你的第一步行动永远是使用 `read_file` 工具读取该技能对应的 `location` 路径下的 Markdown 文件。
2. 仔细阅读文件中的内容、步骤和示例。
3. 根据文件中的指示，结合你内置的 Core Tools (terminal, python_repl, fetch_url) 来执行具体任务。
**禁止**直接猜测技能的参数或用法，必须先读取文件！

## 技能创建协议 (SKILL CREATION PROTOCOL)
当用户要求创建新技能时，必须遵守以下格式规范：
1. 在 skills/ 目录下创建以技能名命名的文件夹（英文、小写、下划线分隔）。
2. 在该文件夹内创建 SKILL.md 文件，必须以 YAML Frontmatter 开头：
   ---
   name: skill_name
   description: 技能的中文描述
   ---
3. 禁止省略 Frontmatter，否则系统无法正确识别技能。

## 记忆协议
...
```

### 4. 会话存储 (Sessions)
+ **路径**：`backend/sessions/{session_name}.json`
+ **格式**：标准 JSON 数组，包含 `user`, `assistant`, `tool` (function calls) 类型的完整消息记录。

## 五、后端 API 接口规范 (FastAPI)
后端服务作为独立进程运行，负责 Agent 逻辑、文件读写和状态管理。

+ **服务端口**：`8088`
+ **基础 URL**：`http://localhost:8088`

### 1. 核心对话接口
+ **Endpoint**: `POST /api/chat`
+ **功能**: 发送用户消息，获取 Agent 回复。
+ **Request**:

```plain
{
  "message": "查询一下北京的天气",
  "session_id": "main_session",
  "stream": true
}
```

+ **Response**: 支持 **SSE (Server-Sent Events)** 流式输出，实时推送 Agent 的思考过程 (Thought/Tool Calls) 和最终回复。

### 2. 文件管理接口 (用于前端编辑器)
+ **Endpoint**: `GET /api/files` - 读取指定文件内容（Query: `path=memory/MEMORY.md`）。
+ **Endpoint**: `POST /api/files` - 保存文件修改（Body: `{ "path": "...", "content": "..." }`）。
+ **Endpoint**: `GET /api/files/tree` - 获取项目文件树结构（Query: `root=`，可选子目录）。

### 3. 会话管理接口
+ **Endpoint**: `GET /api/sessions` - 获取所有历史会话列表。
+ **Endpoint**: `GET /api/sessions/{session_id}` - 获取指定会话的消息记录。
+ **Endpoint**: `POST /api/sessions` - 创建新会话。
+ **Endpoint**: `DELETE /api/sessions/{session_id}` - 删除指定会话。

### 4. 技能管理接口
+ **Endpoint**: `GET /api/skills` - 获取所有已安装技能列表（含 name, description, location）。
+ **Endpoint**: `DELETE /api/skills/{skill_name}` - 删除指定技能（删除整个技能文件夹）。

### 5. 知识库接口
+ **Endpoint**: `POST /api/knowledge/rebuild` - 强制重建 RAG 知识库索引。

### 6. 设置管理接口
+ **Endpoint**: `GET /api/settings` - 获取当前模型配置（LLM/Embedding 的 API Key、Base URL、模型名称、Temperature、Max Tokens 等），数据读取自 `.env` 文件。
+ **Endpoint**: `PUT /api/settings` - 更新模型配置，写回 `.env` 文件（保留注释和原有结构）。修改后需重启后端生效。

### 7. 健康检查
+ **Endpoint**: `GET /api/health` - 返回后端状态、版本号和当前模型名称。

### 8. 技能商店接口 ✅ 已实现
+ **Endpoint**: `GET /api/store/skills` - 获取远程技能列表。
    - Query 参数：`category`（分类筛选）、`page`（页码）、`page_size`（每页数量）
    - 返回：技能列表、总数、版本号
+ **Endpoint**: `GET /api/store/search` - 搜索技能。
    - Query 参数：`q`（搜索关键词）
    - 返回：匹配的技能列表
+ **Endpoint**: `GET /api/store/skills/{name}` - 获取技能详情。
    - 返回：技能元数据、SKILL.md 内容、所需工具等
+ **Endpoint**: `POST /api/store/install` - 安装技能。
    - Body: `{ "skill_name": "...", "version": "..." }`
    - 返回：安装状态和消息
+ **Endpoint**: `POST /api/skills/{skill_name}/update` - 更新已安装技能。
+ **Endpoint**: `GET /api/store/categories` - 获取可用分类列表。

### 9. 翻译接口 ✅ 已实现
+ **Endpoint**: `POST /api/translate` - 翻译内容为中文。
    - Body: `{ "content": "...", "target_language": "zh-CN" }`
    - 返回：`{ "status": "ok", "translated": "...", "source_language": "en", "target_language": "zh-CN" }`
    - 说明：使用 LLM 进行智能翻译，仅翻译描述性文本，保留代码块和技术标识符。

## 六、前端开发要求
### 1. 设计理念与布局架构
前端采用 **IDE（集成开发环境）风格**，**可拖拽调整宽度的三栏式布局**。

+ **左侧 (Sidebar)**：导航 (Chat/Memory/Skills) + 会话列表。
    - 宽度范围：200px ~ 400px（默认 256px），可拖拽调整。
    - 会话标题：最多显示两行，超出截断；无消息的新会话显示「新会话」。
    - 技能列表：每项右侧显示删除按钮（hover 可见），点击弹出确认后删除。
+ **中间 (Stage)**：对话流 + **思考链可视化** (Collapsible Thoughts)。
    - 宽度自适应填充剩余空间。
    - **工具调用友好化展示**：
        * 工具名称映射为中文标签 + Emoji（如 `read_file` -> 📄 读取文件）。
        * 输入参数从 JSON 中提取关键信息作为摘要显示。
        * 展开详情后，Input 和 Output 均使用 Markdown 渲染（代码块语法高亮、标题、列表等），`\n` 自动转换为实际换行。
+ **右侧 (Inspector)**：Monaco Editor，用于实时查看/编辑正在使用的 `SKILL.md` 或 `MEMORY.md`。
    - 宽度范围：280px ~ 600px（默认 384px），可拖拽调整。
+ **分隔条**：宽 4px，hover 显示蓝色半透明高亮，拖拽中高亮加深。

### 2. 技术栈
+ **框架**: Next.js 14+ (App Router), TypeScript
+ **UI**: Shadcn/UI, Tailwind CSS v4, Lucide Icons
+ **Editor**: Monaco Editor (配置为 Light Theme)
+ **Markdown 渲染**: react-markdown + remark-gfm
+ **代码语法高亮**: react-syntax-highlighter (Prism, oneLight 主题)
+ **字体**: Google Fonts (Inter + JetBrains Mono)，通过 layout.tsx 中 link 标签引入

### 3. UI/UX 风格规范
+ **色调**: **浅色 Apple 风格 (Frosty Glass)**。
    - 背景：纯白/极浅灰 (`#fafafa`)，高透毛玻璃效果。
    - 强调色：**支付宝蓝** (Alipay Blue) 或 **阿里橙**。
+ **导航栏**: 顶部固定，半透明。
    - 左侧：**"VibeWorker"** + 版本号
    - 右侧：后端状态指示器（在线/离线）+ ⚙️ 设置按钮（弹窗配置 LLM/Embedding 模型参数）+ Inspector 开关按钮
+ **设置弹窗 (Settings Dialog)**：
    - 点击导航栏设置按钮打开，分「LLM 模型」和「Embedding 模型」两个分组。
    - 支持配置 API Key（密码模式，可切换显示）、API Base URL、模型名称、Temperature、Max Tokens。
    - 保存后自动关闭弹窗，配置写入后端 `.env` 文件。
+ **代码块样式**：
    - 工具调用详情中的代码块采用浅色背景（`#f6f8fb`）+ 蓝色左边条 + Prism 语法高亮。
    - 使用 JetBrains Mono 等宽字体，字号 `0.7rem`。


## 七、项目目录结构参考
建议 Claude Code 按照以下结构进行初始化：

```plain
vibeworker/
├── backend/                # FastAPI + LangChain/LangGraph
│   ├── app.py              # 入口文件 (Port 8088)
│   ├── config.py           # Pydantic Settings 配置管理
│   ├── prompt_builder.py   # System Prompt 动态拼接
│   ├── sessions_manager.py # 会话管理器
│   ├── .env                # 环境变量 (API Key 等)
│   ├── store/              # 技能商店模块 ✅
│   │   ├── __init__.py     # SkillsStore 核心逻辑 (skills.sh 集成)
│   │   └── models.py       # Pydantic 模型 (RemoteSkill, SkillDetail 等)
│   ├── memory/             # 记忆存储
│   │   ├── logs/           # Daily logs
│   │   └── MEMORY.md       # Core memory
│   ├── sessions/           # JSON 会话记录
│   ├── skills/             # Agent Skills 文件夹 (本地已安装技能)
│   ├── workspace/          # System Prompts (SOUL.md, AGENTS.md, etc.)
│   ├── tools/              # Core Tools 实现
│   ├── graph/              # LangGraph Agent 编排
│   │   └── agent.py        # create_agent 配置
│   ├── knowledge/          # RAG 知识库文档存放
│   ├── storage/            # 索引持久化存储
│   └── requirements.txt
│
├── frontend/               # Next.js 14+ (App Router)
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx  # 根布局 (字体引入)
│   │   │   ├── page.tsx    # 三栏可拖拽布局
│   │   │   └── globals.css # 全局 CSS 主题与组件样式
│   │   ├── components/
│   │   │   ├── chat/       # ChatPanel (对话流 + 工具调用可视化)
│   │   │   ├── sidebar/    # Sidebar (会话/记忆/技能导航 + 商店入口)
│   │   │   ├── editor/     # InspectorPanel (Monaco Editor + 翻译功能)
│   │   │   ├── store/      # 技能商店组件 ✅
│   │   │   │   ├── SkillsStoreDialog.tsx  # 商店弹窗主组件
│   │   │   │   ├── SkillCard.tsx          # 技能卡片
│   │   │   │   └── SkillDetail.tsx        # 技能详情页
│   │   │   ├── settings/   # SettingsDialog (模型配置弹窗)
│   │   │   └── ui/         # Shadcn/UI 基础组件
│   │   └── lib/
│   │       └── api.ts      # API 客户端 (含 Store/Translate API)
│   └── package.json
│
├── scripts/                # CLI 工具 ✅
│   ├── skills.sh           # Linux/macOS 技能管理脚本
│   └── skills.bat          # Windows 技能管理脚本
│
└── README.md
```

