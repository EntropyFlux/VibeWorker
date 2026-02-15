# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

**VibeWorker** 是一个基于 Python 构建的轻量级 AI 数字员工 Agent 系统，运行在本地。核心特性：
- **文件即记忆 (File-first Memory)**：所有记忆以 Markdown/JSON 文件形式存储（人类可读，完全透明）
- **技能即插件 (Skills as Plugins)**：遵循 Anthropic Agent Skills 范式，通过文件夹结构管理能力（拖入即用）
- **透明可控**：所有 System Prompt 拼接逻辑、工具调用、记忆操作对开发者完全透明

## 技术栈

| 组件 | 技术 |
|------|------|
| **后端框架** | FastAPI (Python 3.10+) |
| **Agent 编排** | LangChain 1.x (Stable) + LangGraph |
| **RAG 检索** | LlamaIndex (Hybrid Search) |
| **前端框架** | Next.js 14+ (App Router) |
| **UI 组件库** | Shadcn/UI + Tailwind CSS v4 |
| **代码编辑器** | Monaco Editor |
| **MCP 集成** | MCP Python SDK (Anthropic 官方) |
| **存储方案** | 本地文件系统（无 MySQL/Redis 等重依赖） |

## 开发命令速查

### 后端启动
```bash
cd backend
pip install -r requirements.txt
python app.py
# 服务启动在 http://localhost:8088
```

### 前端启动
```bash
cd frontend
npm install
npm run dev
# 前端启动在 http://localhost:3000
```

### 前端构建 & 检查
```bash
npm run build  # 生产构建
npm lint       # 运行 ESLint
```

---

## 后端架构

### 1. Agent 编排引擎 (LangGraph-based)

**关键文件：** `backend/graph/agent.py`

**重要约束：**
- ✅ **必须** 使用 `langchain.agents.create_agent` API（LangChain 1.0+ 标准）
- ❌ **严禁** 使用旧版 `AgentExecutor` 或早期 `create_react_agent`
- `create_agent` 底层基于 LangGraph 运行时，提供标准化接口

**工作流程：**
1. LLM (configurable) 接收 System Prompt
2. 识别需要调用的 Core Tool
3. 执行 Tool，获得结果
4. 迭代，直到完成或达到最大步数
5. 通过 SSE 流式返回思考过程和最终回复

### 2. Core Tools（7 个内置工具）

所有 Core Tools 均使用 LangChain 原生实现，存放在 `backend/tools/`。

| 工具名称 | 功能 | LangChain 组件 | 配置要点 |
|---------|------|----------------|---------|
| **terminal** | Shell 命令执行（受限沙箱） | `langchain_community.tools.ShellTool` | 必须设置 `root_dir` 限制范围，黑名单拦截高危指令 |
| **python_repl** | Python 代码执行 & 数据处理 | `langchain_experimental.tools.PythonREPLTool` | 自动创建临时交互环境；来自 experimental 包，需确保依赖正确 |
| **fetch_url** | 网页内容获取（Agent 联网核心） | `langchain_community.tools.RequestsGetTool` (需 Wrapper) | **必须包装**：原生返回 HTML 效率低，用 BeautifulSoup/html2text 清洗返回 Markdown 或纯文本 |
| **read_file** | 读取本地文件内容（Skills 机制依赖） | `langchain_community.tools.file_management.ReadFileTool` | 必须设置 `root_dir` 为项目根目录，禁止读取系统外文件 |
| **search_knowledge_base** | RAG 混合检索 | LlamaIndex (Hybrid: BM25 + Vector) | 扫描 `knowledge/` 构建索引，持久化存储在 `storage/` |
| **memory_write** | 记忆写入（长期记忆或每日日志） | 自定义 `@tool`，调用 `MemoryManager` | 支持 `write_to="memory"/"daily"`，自动去重、分类管理 |
| **memory_search** | 记忆搜索（语义+关键词） | 自定义 `@tool` + LlamaIndex | 优先语义搜索，降级为关键词匹配；索引持久化到 `storage/memory_index/` |

### 3. 缓存系统 (Cache System)

**关键文件：** `backend/cache/`

**架构设计：** 双层缓存（L1 内存 + L2 磁盘）

**设计原则：**
- ✅ **无外部依赖**：纯 Python 实现，无需 Redis/Memcached
- ✅ **文件即缓存**：所有缓存以 JSON 文件存储在 `.cache/` 目录（透明可审计）
- ✅ **可配置性**：通过 `.env` 文件灵活控制开关、TTL、大小限制
- ✅ **向后兼容**：默认配置不影响现有功能

**缓存类型与配置：**

| 缓存类型 | 默认状态 | 默认 TTL | 存储位置 | 用途 |
|---------|---------|----------|----------|------|
| **URL 缓存** | ✅ 开启 | 1 小时 | `.cache/url/` | 网页请求结果（fetch_url 工具） |
| **LLM 缓存** | ❌ 关闭 | 24 小时 | `.cache/llm/` | Agent 响应（含流式模拟） |
| **Prompt 缓存** | ✅ 开启 | 10 分钟 | `.cache/prompt/` | System Prompt 拼接结果 |
| **翻译缓存** | ✅ 开启 | 7 天 | `.cache/translate/` | 翻译 API 结果 |
| **MCP 工具缓存** | ✅ 开启 | 1 小时 | `.cache/tool_mcp_*/` | MCP 工具调用结果（自动按工具名分目录） |

**注意：**
- `.cache/` 目录已添加到 `.gitignore`，不会上传到 git
- LLM 缓存默认关闭，避免影响 Agent 的探索性和多样性
- 用户可在前端设置页面手动清理缓存

**工作原理：**

1. **L1 内存缓存 (MemoryCache)**
   - Python dict + TTL + LRU 淘汰
   - 毫秒级访问速度
   - 默认最多缓存 100 项

2. **L2 磁盘缓存 (DiskCache)**
   - JSON 文件存储（两级目录结构：`{key[:2]}/{key}.json`）
   - 持久化，进程重启后可复用
   - 定时清理（每小时）+ LRU 淘汰（超过 5GB 时）

3. **缓存键生成**
   - URL 缓存：`SHA256(url)`
   - LLM 缓存：`SHA256(system_prompt_hash + recent_history + message + model + temperature)`
   - Prompt 缓存：`SHA256(workspace_files_mtime)`
   - 翻译缓存：`SHA256(content + target_language)`
   - MCP 工具缓存：`SHA256(tool_name + json(args))`

**流式缓存处理：**

LLM 缓存支持流式输出模拟：
- 缓存完整响应（包含所有 tokens 和 tool_calls）
- 命中缓存时，逐字符分块 yield，模拟流式效果
- 添加短暂延迟（10ms/chunk）保持用户体验一致性
- 事件中添加 `"cached": true` 标记（可选）

**配置示例 (.env)：**

```bash
# Cache Configuration
ENABLE_URL_CACHE=true
ENABLE_LLM_CACHE=false          # 默认关闭
ENABLE_PROMPT_CACHE=true
ENABLE_TRANSLATE_CACHE=true
MCP_ENABLED=true                # MCP 模块总开关

URL_CACHE_TTL=3600              # 1 hour
LLM_CACHE_TTL=86400             # 24 hours
PROMPT_CACHE_TTL=600            # 10 minutes
TRANSLATE_CACHE_TTL=604800      # 7 days

CACHE_MAX_MEMORY_ITEMS=100
CACHE_MAX_DISK_SIZE_MB=5120     # 5GB
MCP_TOOL_CACHE_TTL=3600         # 1 hour (MCP 工具缓存 TTL)
```

**管理 API：**

```bash
GET  /api/cache/stats           # 获取缓存统计信息
POST /api/cache/clear?type=url  # 清空指定类型缓存（url/llm/prompt/translate/all）
POST /api/cache/cleanup         # 清理过期缓存 + LRU 淘汰
```

**性能提升：**

| 操作 | 优化前 | 优化后（缓存命中） | 提升 |
|------|--------|------------------|------|
| 网页请求 | ~500-2000ms | ~10-50ms | **10-100x** |
| LLM 调用 | ~2000-5000ms | ~100-300ms（模拟流） | **10-20x** |
| Prompt 拼接 | ~50-100ms | ~1-5ms | **10-50x** |
| 翻译 API | ~1000-2000ms | ~5-20ms | **50-200x** |

### 4. Agent Skills 系统（指令遵循范式）

**原理：**
- Skills 是 **教学说明书**，不是预写函数
- Agent 通过**阅读 SKILL.md 文件**来学习如何使用 Core Tools 完成任务
- 核心工作流：`识别 Skill → read_file(SKILL.md) → 理解步骤 → 调用 Core Tools`

**目录结构：**
```
backend/skills/
├── get_weather/                  # Skill 文件夹（英文小写下划线分隔）
│   └── SKILL.md                  # 必须包含 YAML Frontmatter
├── get_recent_movies/
│   └── SKILL.md
└── ...
```

**SKILL.md 格式规范：**
```markdown
---
name: skill_name              # 技能英文名称（与文件夹名一致）
description: 技能中文描述     # 一句话概括功能
---

# 技能标题

## 描述
详细说明...

## 使用方法
### 步骤 1: ...
### 步骤 2: ...

### 备注
- ...
```

**关键规则：**
- Frontmatter (`---` 包裹) 必须出现在文件第 1-3 行，否则系统无法识别
- 不允许省略 Frontmatter

**Skills 加载流程：**
1. 系统启动时，扫描 `backend/skills/` 目录
2. 读取每个 `SKILL.md` 的 Frontmatter，生成 `SKILLS_SNAPSHOT` XML
3. SKILLS_SNAPSHOT 注入到 System Prompt，Agent 可感知可用技能
4. Agent 调用 `read_file(./backend/skills/{skill_name}/SKILL.md)` 时，获得详细步骤
5. 根据步骤，动态调用 Core Tools（terminal/python_repl/fetch_url）执行

**Claude Code 兼容性：**
- 系统可兼容本地 Claude Code 插件安装的 Skills
- 若本地有 Claude Code，Agent 可同时使用其 Skills
- 若无 Claude Code，也不影响运行

### 5. MCP (Model Context Protocol) 集成

**关键文件：** `backend/mcp_module/`

**概述：** VibeWorker 作为 MCP Client，连接外部 MCP Server，将其暴露的工具动态注入到 Agent 中。

**模块结构：**
```
backend/mcp_module/
├── __init__.py          # 导出 MCPManager 单例（mcp_manager）
├── config.py            # mcp_servers.json 配置读写
├── manager.py           # MCPManager: 连接管理、工具发现、生命周期
└── tool_wrapper.py      # MCP 工具 → LangChain StructuredTool 包装（含 L1+L2 缓存）
```

**配置文件：** `backend/mcp_servers.json`
```json
{
  "servers": {
    "filesystem": {
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
      "env": {},
      "enabled": true,
      "description": "本地文件系统访问"
    },
    "brave-search": {
      "transport": "sse",
      "url": "http://localhost:3001/sse",
      "headers": {},
      "enabled": true,
      "description": "Brave 搜索引擎"
    }
  }
}
```

**支持的传输方式：**
- `stdio`：本地进程（command + args + env）
- `sse`：远程 HTTP（url + headers）

**MCPManager 核心方法：**
| 方法 | 功能 |
|------|------|
| `initialize()` | 启动时连接所有 enabled 的 server |
| `shutdown()` | 关闭所有连接 |
| `connect_server(name)` | 连接指定 server |
| `disconnect_server(name)` | 断开指定 server |
| `get_all_mcp_tools()` | 返回所有已连接 server 的 LangChain 工具 |
| `get_server_status()` | 返回各 server 状态 |
| `get_server_tools(name)` | 返回指定 server 的工具列表 |

**工具包装机制：**
- 每个 MCP 工具 → 一个独立的 LangChain `StructuredTool`
- 工具名格式：`mcp_{server_name}_{tool_name}`（避免与 Core Tools 命名冲突）
- 工具描述直接使用 MCP 工具的 description
- 调用时通过 MCPManager 转发到对应的 MCP Server session

**缓存集成：**
- 每个 MCP 工具有独立的 L1（内存）+ L2（磁盘）缓存
- 缓存目录：`.cache/tool_mcp_{server}_{tool}/`
- TTL 使用 `MCP_TOOL_CACHE_TTL` 配置（默认 1 小时）
- 命中时返回 `[CACHE_HIT]` 前缀标记

**工具注入：**
- `backend/tools/__init__.py` 的 `get_all_tools()` 自动追加 MCP 工具
- MCP 不可用时不影响 7 个 Core Tools

**生命周期（app.py lifespan）：**
- 启动时：`mcp_manager.initialize()`（连接所有 enabled server）
- 关闭时：`mcp_manager.shutdown()`（优雅断开所有连接）
- 连接状态：`disconnected` → `connecting` → `connected` / `error`
- 单个 server 错误不影响其他 server 或 Core Tools

**注意事项：**
- 模块目录为 `mcp_module/`（非 `mcp/`），避免与 pip 包 `mcp` 的 import 冲突
- `from mcp import ClientSession` 引用的是 pip 包，`from mcp_module import mcp_manager` 引用的是本地模块

### 6. System Prompt 动态拼接

**文件位置：** `backend/workspace/`

System Prompt 由以下部分顺序拼接而成（按顺序）：

```
1. SKILLS_SNAPSHOT.xml    ← 能力列表（自动生成）
2. SOUL.md                ← 核心设定
3. IDENTITY.md            ← 自我认知
4. USER.md                ← 用户画像
5. AGENTS.md              ← 行为准则 & 记忆操作指南（最关键）
6. MEMORY.md              ← 长期记忆
7. Daily Logs             ← 今天+昨天的每日日志（自动加载）
```

**截断策略：**
- 若拼接后超出模型 Token 限制（或单文件超 20k 字符），截断并在末尾添加 `...[truncated]`
- 记忆部分有独立 Token 预算（`MEMORY_MAX_PROMPT_TOKENS`，默认 4000），优先级：MEMORY.md > 今天 > 昨天
- 由 `prompt_builder.py` 负责拼接逻辑

**AGENTS.md 的必要内容：**
必须包含明确的元指令，告诉 Agent **如何使用 Skills 和记忆系统**：

```markdown
# 操作指南

## 技能调用协议 (SKILL PROTOCOL)
（省略，详见 backend/workspace/AGENTS.md）

## 技能创建协议 (SKILL CREATION PROTOCOL)
（省略，详见 backend/workspace/AGENTS.md）

## 记忆协议 (MEMORY PROTOCOL)
- 声明 `memory_write` 和 `memory_search` 两个专用工具
- 说明长期记忆（MEMORY.md）vs 每日日志（Daily Logs）的使用场景
- **必须**使用 `memory_write` 写入记忆，**禁止** `terminal echo >>`
- **必须**使用 `memory_search` 搜索历史记忆
- 分类说明：preferences/facts/tasks/reflections/general

## 对话协议 (CHAT PROTOCOL)
（省略，详见 backend/workspace/AGENTS.md）
```

### 7. 会话管理

**会话存储：** `backend/sessions/{session_name}.json`

**格式：** 标准 JSON 数组，包含完整消息记录：
```json
[
  { "type": "user", "content": "...", "timestamp": "..." },
  { "type": "assistant", "content": "..." },
  { "type": "tool", "tool_name": "read_file", "input": {...}, "output": "..." }
]
```

### 8. 配置管理

**文件：** `backend/config.py`（Pydantic Settings）

**关键配置项：**
- `llm_api_key`：LLM API 密钥（支持 OpenAI/OpenRouter/Zenmux 等兼容格式）
- `llm_api_base`：API 端点（默认 https://api.openai.com/v1）
- `llm_model`：模型名称（默认 gpt-4o）
- `llm_temperature`：采样温度（默认 0.7）
- `llm_max_tokens`：最大输出（默认 4096）
- `embedding_api_key`、`embedding_api_base`、`embedding_model`：向量模型配置
- 目录路径：`memory_dir`, `sessions_dir`, `skills_dir`, `workspace_dir`, `knowledge_dir`, `storage_dir`
- 记忆配置：`memory_auto_extract`(自动提取), `memory_daily_log_days`(日志天数), `memory_max_prompt_tokens`(Token预算), `memory_index_enabled`(索引开关)
- MCP 配置：`mcp_enabled`(MCP 总开关), `mcp_tool_cache_ttl`(工具缓存 TTL)

**环境变量优先级：**
- 优先读取 `.env` 文件中的 `LLM_API_KEY` 等
- 其次尝试 `OPENAI_API_KEY`（兼容性）
- `model_post_init()` 自动映射环境变量

---

## 后端 API 接口规范

**服务地址：** `http://localhost:8088`

### 1. 对话接口
```
POST /api/chat
Request: {
  "message": "用户消息",
  "session_id": "main_session",  # 可选，默认 main_session
  "stream": true                  # 可选，默认 true，支持 SSE
}
Response: Server-Sent Events 流式响应
```

### 2. 文件管理接口
```
GET /api/files?path=memory/MEMORY.md       # 读取文件
POST /api/files                            # 保存文件 { "path": "...", "content": "..." }
GET /api/files/tree?root=...              # 获取文件树结构
```

### 3. 会话管理接口
```
GET /api/sessions                          # 获取所有会话列表
GET /api/sessions/{session_id}            # 获取指定会话消息
POST /api/sessions                         # 创建新会话 { "session_id": "..." }
DELETE /api/sessions/{session_id}         # 删除会话
```

### 4. 技能管理接口
```
GET /api/skills                           # 获取所有技能列表（含 name, description, location）
DELETE /api/skills/{skill_name}           # 删除技能（删除整个技能文件夹）
```

### 5. 知识库接口
```
POST /api/knowledge/rebuild               # 强制重建 RAG 索引
```

### 6. 记忆管理接口
```
GET  /api/memory/entries                  # 列出 MEMORY.md 条目（支持分类筛选、分页）
POST /api/memory/entries                  # 添加记忆条目 {content, category}
DELETE /api/memory/entries/{entry_id}     # 删除单条记忆
GET  /api/memory/daily-logs              # 列出所有 Daily Log 文件
GET  /api/memory/daily-logs/{date}       # 获取指定日期的日志内容
POST /api/memory/search                  # 搜索记忆 {query, top_k}
GET  /api/memory/stats                   # 记忆统计信息
POST /api/memory/reindex                 # 强制重建记忆索引
```

### 7. MCP 管理接口
```
GET  /api/mcp/servers                    # 列出所有 MCP Server 及状态
POST /api/mcp/servers/{name}             # 添加新 MCP Server
PUT  /api/mcp/servers/{name}             # 更新 MCP Server 配置
DELETE /api/mcp/servers/{name}           # 删除 MCP Server
POST /api/mcp/servers/{name}/connect     # 手动连接
POST /api/mcp/servers/{name}/disconnect  # 手动断开
GET  /api/mcp/tools                      # 列出所有已发现的 MCP 工具
GET  /api/mcp/servers/{name}/tools       # 列出指定 Server 的工具
```

### 8. 设置管理接口
```
GET /api/settings                         # 获取配置（从 .env 读取，含记忆/缓存/MCP 配置）
PUT /api/settings                         # 更新配置（写入 .env，需重启后端生效）
```

### 9. 健康检查
```
GET /api/health                           # 返回状态、版本、当前模型名
```

---

## 前端架构

### UI 布局（IDE 风格三栏可拖拽）

```
┌─────────────────────────────────────────────────────────┐
│ TopBar: VibeWorker v0.1.0 | 后端状态 | ⚙️ | 📄 Inspector │
├──────────────┬──────────────────────────────┬───────────┤
│              │                              │           │
│  Sidebar     │       Chat Stage             │ Inspector │
│  (256px)     │   (自适应)                    │  (384px)  │
│  ───────     │                              │           │
│  • 新建       │  消息流 + 工具调用展示       │ Monaco    │
│  • 会话列表   │  - 思考链 (可折叠)          │ Editor    │
│  • 记忆      │  - 工具调用中文化            │           │
│  • 技能      │  - Markdown 渲染            │           │
│  • MCP       │  - 代码高亮                  │           │
│  • 缓存      │                              │           │
└──────────────┴──────────────────────────────┴───────────┘
```

**宽度范围：**
- Sidebar：200px ~ 400px（默认 256px），可拖拽调整
- Inspector：280px ~ 600px（默认 384px），可拖拽调整
- 分隔条：4px，hover 蓝色半透明，拖拽时加深

### 前端组件结构

```
frontend/src/
├── app/
│   ├── layout.tsx              # 根布局（字体引入：Inter + JetBrains Mono）
│   ├── page.tsx                # 三栏可拖拽主布局
│   └── globals.css             # 主题色、组件样式、工具调用样式
├── components/
│   ├── chat/                   # ChatPanel（消息流 + 工具调用可视化）
│   ├── sidebar/                # Sidebar（导航 + 会话/记忆/技能/MCP/缓存列表）
│   │   ├── MemoryPanel.tsx     # 记忆面板（三 Tab：记忆/日记/人格）
│   │   ├── McpPanel.tsx        # MCP 管理面板（Server 列表/状态/工具/操作）
│   │   ├── McpServerDialog.tsx # MCP Server 添加/编辑弹窗
│   │   └── CachePanel.tsx      # 缓存管理面板（accordion 展开模式）
│   ├── editor/                 # InspectorPanel（Monaco Editor）
│   ├── settings/               # SettingsDialog（通用/模型/记忆/缓存 四 Tab）
│   └── ui/                     # Shadcn/UI 基础组件
└── lib/
    └── api.ts                  # API 客户端（Chat/Sessions/Files/Settings/Memory...）
```

### UI/UX 规范

**色调：** 浅色 Apple 风格（Frosty Glass）
- 背景：纯白/极浅灰 (`#fafafa`)，高透毛玻璃效果
- 强调色：支付宝蓝或阿里橙

**导航栏：** 顶部固定，半透明
- 左：VibeWorker + 版本号
- 右：后端状态指示 → LLM/Embedding 模型参数设置 ⚙️ → Inspector 切换 📄

**工具调用展示（中间栏）：**
- Core Tools 名映射为中文 + Emoji（如 `read_file` → 📄 读取文件）
- MCP 工具动态显示为 🔌 MCP: {tool_name} 格式
- Input/Output 使用 Markdown 渲染（代码块语法高亮、标题、列表等）
- 代码块样式：浅灰背景 (`#f6f8fb`) + 蓝色左边条 + Prism 高亮 + JetBrains Mono 字体

**设置弹窗（四 Tab）：**
- **通用**：主题切换（明亮/暗黑模式）
- **模型**：LLM / Embedding / 翻译 三个子 Tab，配置 API Key、Base URL、模型名等
- **记忆**：自动提取、语义索引、日志天数、Token 预算
- **缓存**：URL / LLM / Prompt / 翻译 / MCP 工具缓存的开关控制
- 保存后自动关闭，配置写入后端 `.env`

### 重要技术选择

| 库 | 用途 | 版本要求 |
|----|------|---------|
| Next.js | App Router | 14+ |
| Shadcn/UI | UI 组件库 | 最新 |
| Tailwind CSS | 样式 | v4 |
| Monaco Editor | 代码编辑 | 最新 |
| react-markdown | Markdown 渲染 | 最新 |
| remark-gfm | GitHub Flavored Markdown | 最新 |
| react-syntax-highlighter | 代码高亮 | Prism + oneLight 主题 |
| Lucide Icons | 图标库 | 最新 |
| mcp (Python) | MCP Client SDK | >=1.0.0 |

---

## 项目目录结构

```
E:\code\opensre/
├── backend/
│   ├── app.py                  # FastAPI 入口（Port 8088）
│   ├── config.py               # Pydantic Settings
│   ├── prompt_builder.py       # System Prompt 动态拼接
│   ├── sessions_manager.py     # 会话管理器
│   ├── .env                    # 环境变量（API Key 等）
│   ├── requirements.txt        # Python 依赖
│   ├── memory_manager.py        # 记忆管理中心（MemoryManager 核心类）
│   ├── memory/
│   │   ├── logs/               # Daily Logs（每日日志，YYYY-MM-DD.md）
│   │   └── MEMORY.md           # 长期记忆（按分类组织的结构化条目）
│   ├── sessions/               # JSON 会话记录
│   ├── skills/                 # Agent Skills（用户自定义）
│   │   ├── get_weather/
│   │   │   └── SKILL.md
│   │   └── get_recent_movies/
│   │       └── SKILL.md
│   ├── workspace/              # System Prompts
│   │   ├── AGENTS.md           # 行为准则 & 记忆操作指南
│   │   ├── SOUL.md             # 核心设定
│   │   ├── IDENTITY.md         # 自我认知
│   │   └── USER.md             # 用户画像
│   ├── tools/                  # Core Tools 实现（7 个内置工具）
│   │   ├── __init__.py         # get_all_tools()
│   │   ├── terminal_tool.py
│   │   ├── python_repl_tool.py
│   │   ├── fetch_url_tool.py
│   │   ├── read_file_tool.py
│   │   ├── rag_tool.py
│   │   ├── memory_write_tool.py    # 记忆写入工具
│   │   └── memory_search_tool.py   # 记忆搜索工具
│   ├── mcp_module/             # MCP (Model Context Protocol) 模块
│   │   ├── __init__.py         # MCPManager 单例导出
│   │   ├── config.py           # mcp_servers.json 配置读写
│   │   ├── manager.py          # MCPManager 核心（连接管理、工具发现）
│   │   └── tool_wrapper.py     # MCP 工具 → LangChain StructuredTool（含缓存）
│   ├── mcp_servers.json        # MCP Server 配置文件
│   ├── graph/                  # LangGraph Agent
│   │   └── agent.py            # create_agent 配置
│   ├── cache/                  # 缓存系统模块
│   │   ├── __init__.py         # 缓存实例导出
│   │   ├── base.py             # 基础接口
│   │   ├── memory_cache.py     # L1 内存缓存
│   │   ├── disk_cache.py       # L2 磁盘缓存
│   │   ├── url_cache.py        # URL 缓存
│   │   ├── llm_cache.py        # LLM 缓存
│   │   ├── prompt_cache.py     # Prompt 缓存
│   │   └── translate_cache.py  # 翻译缓存
│   ├── .cache/                 # 缓存存储目录（不上传 git）
│   │   ├── url/                # URL 缓存文件
│   │   ├── llm/                # LLM 缓存文件
│   │   ├── prompt/             # Prompt 缓存文件
│   │   ├── translate/          # 翻译缓存文件
│   │   └── tool_mcp_*/         # MCP 工具缓存文件（按工具名自动创建）
│   ├── knowledge/              # RAG 知识库文档（PDF/MD/TXT）
│   └── storage/                # 索引持久化存储
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx      # 根布局
│   │   │   ├── page.tsx        # 三栏主布局
│   │   │   └── globals.css     # 主题 & 样式
│   │   ├── components/
│   │   │   ├── chat/
│   │   │   ├── sidebar/
│   │   │   │   ├── MemoryPanel.tsx  # 记忆面板（三 Tab）
│   │   │   │   ├── McpPanel.tsx     # MCP 管理面板
│   │   │   │   ├── McpServerDialog.tsx # MCP Server 添加/编辑弹窗
│   │   │   │   └── CachePanel.tsx   # 缓存管理面板
│   │   │   ├── editor/
│   │   │   ├── settings/
│   │   │   └── ui/
│   │   └── lib/
│   │       └── api.ts          # API 客户端
│   ├── package.json
│   └── tsconfig.json
│
├── README.md
└── CLAUDE.md (this file)
```

---

## 开发指南

### 添加新 Tool
1. 在 `backend/tools/` 下创建 `{tool_name}_tool.py`
2. 使用 LangChain 原生工具或创建 Tool 包装类
3. 在 `backend/tools/__init__.py` 中导出 `create_{tool_name}_tool()`
4. 在 `get_all_tools()` 中添加新工具

### 创建新 Skill
1. 在 `backend/skills/{skill_name}/` 目录下创建 `SKILL.md`
2. 必须包含 YAML Frontmatter（name + description）
3. 在 Markdown 正文中详细描述步骤和使用方法
4. Agent 会自动发现并加载（通过 SKILLS_SNAPSHOT 机制）

### 修改 System Prompt
1. 编辑 `backend/workspace/` 下的文件（AGENTS.md, SOUL.md, IDENTITY.md, USER.md）
2. 修改会自动反映在下一次请求的 System Prompt 中（无需重启）
3. 若需调整拼接顺序或截断逻辑，修改 `backend/prompt_builder.py`

### 配置 LLM 参数
1. 编辑 `backend/.env` 文件
2. 支持的环境变量：
   - `LLM_API_KEY` 或 `OPENAI_API_KEY`
   - `LLM_API_BASE`（可选，默认 OpenAI）
   - `LLM_MODEL`（默认 gpt-4o）
   - `LLM_TEMPERATURE`（默认 0.7）
   - `LLM_MAX_TOKENS`（默认 4096）
   - `EMBEDDING_API_KEY`、`EMBEDDING_API_BASE`、`EMBEDDING_MODEL`
3. 修改后需重启后端生效

### 配置 MCP
1. 编辑 `backend/mcp_servers.json` 添加 MCP Server（或通过前端 MCP 面板操作）
2. 支持两种传输方式：
   - **stdio**：`command` + `args` + `env`（本地进程，如 `npx -y @modelcontextprotocol/server-filesystem /tmp`）
   - **sse**：`url` + `headers`（远程 HTTP）
3. 设置 `enabled: true/false` 控制是否自动连接
4. 环境变量：
   - `MCP_ENABLED`（默认 true，MCP 模块总开关）
   - `MCP_TOOL_CACHE_TTL`（默认 3600，MCP 工具缓存 TTL 秒数）
5. 也可通过前端设置弹窗的"缓存" Tab 控制 MCP 开关

### 配置记忆系统
1. 编辑 `backend/.env` 文件
2. 支持的环境变量：
   - `MEMORY_AUTO_EXTRACT`（默认 false，自动提取记忆）
   - `MEMORY_DAILY_LOG_DAYS`（默认 2，加载几天日志到 Prompt）
   - `MEMORY_MAX_PROMPT_TOKENS`（默认 4000，记忆 Token 预算）
   - `MEMORY_INDEX_ENABLED`（默认 true，语义搜索索引开关）
3. 也可通过前端设置弹窗的"记忆"Tab 修改

### 调试技巧

**查看 System Prompt 组成：**
- 检查日志中 `prompt_builder.py` 的输出
- 所有 System Prompt 拼接逻辑完全透明

**检查会话历史：**
- 查看 `backend/sessions/{session_id}.json`
- 包含完整消息记录（user/assistant/tool 类型）

**重建 RAG 索引：**
- 调用 `POST /api/knowledge/rebuild`
- 或手动删除 `backend/storage/` 目录重新初始化

**监控 Agent 思考过程：**
- 前端 Chat 面板实时展示工具调用
- 可折叠展开详细的 Input/Output
- 完全可视化 Agent 的推理链

**调试 MCP 连接：**
- 查看所有 Server 状态：`GET /api/mcp/servers`
- 查看已发现的工具：`GET /api/mcp/tools`
- 检查后端日志中 `MCP server '{name}' connected` 确认连接成功
- MCP 工具在 ChatPanel 中显示为 🔌 MCP: {tool_name}
- 模块目录为 `mcp_module/`（非 `mcp/`），避免与 pip 包冲突

**管理缓存系统：**
- 查看缓存统计：`GET /api/cache/stats`
- 清空指定缓存：`POST /api/cache/clear?type=url` (url/llm/prompt/translate/all)
- 清理过期缓存：`POST /api/cache/cleanup`
- 手动删除缓存文件：直接删除 `backend/.cache/` 目录
- 配置缓存行为：编辑 `backend/.env` 中的 `ENABLE_*_CACHE` 和 `*_CACHE_TTL` 参数
- 测试缓存功能：运行 `python backend/test_cache.py`

---

## 重要约束与最佳实践

✅ **必须做：**
- 使用 LangChain 1.x 的 `create_agent` API
- Skills 必须包含 YAML Frontmatter
- 在 AGENTS.md 中明确说明 Skill 调用协议
- 所有记忆以文件形式存储（Markdown/JSON）
- API 严格按 PRD 规范实现

❌ **严禁：**
- 使用旧版 AgentExecutor 或早期 create_react_agent
- 在数据库中存储 Session 或 Memory（文件系统优先）
- Skills 无 Frontmatter
- 在 System Prompt 中直接写入 Python 函数调用代码

---

## 参考资源

- **PRD 文档：** `VibeWorker 开发需求文档 (PRD).md`
- **LangChain 文档：** https://python.langchain.com/docs/agents/
- **LangGraph 文档：** https://langchain-ai.github.io/langgraph/
- **LlamaIndex 文档：** https://docs.llamaindex.ai/
- **Next.js 文档：** https://nextjs.org/docs
- **FastAPI 文档：** https://fastapi.tiangolo.com/
- **MCP 规范：** https://modelcontextprotocol.io/
- **MCP Python SDK：** https://github.com/modelcontextprotocol/python-sdk
