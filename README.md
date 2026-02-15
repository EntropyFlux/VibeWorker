# VibeWorker

<p align="center">
  <strong>Your Local AI Digital Worker with Real Memory</strong>
</p>

---

VibeWorker 是一个轻量级且高度透明的 AI 数字员工 Agent 系统。它运行在本地，拥有"真实记忆"，可以帮助你处理各类任务——信息检索、数据处理、代码执行、文件管理等。

## 核心特性

- **文件即记忆 (File-first Memory)** — 所有记忆以 Markdown/JSON 文件形式存储，人类可读
- **技能即插件 (Skills as Plugins)** — 通过文件夹结构管理能力，拖入即用
- **技能商店 (Skills Store)** — 集成 [skills.sh](https://skills.sh/) 生态，一键浏览、搜索、安装 500+ 社区技能
- **透明可控** — 所有 Prompt 拼接、工具调用、记忆读写完全透明

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI (Python 3.10+) |
| Agent 引擎 | LangChain 1.x + LangGraph |
| RAG 引擎 | LlamaIndex |
| 前端框架 | Next.js 14+ (App Router) |
| UI 组件 | Shadcn/UI + Tailwind CSS |
| 代码编辑器 | Monaco Editor |

## 快速开始

### 后端启动

```bash
cd backend
pip install -r requirements.txt
python app.py
```

后端将在 `http://localhost:8088` 启动。

### 前端启动

```bash
cd frontend
npm install
npm run dev
```

前端将在 `http://localhost:3000` 启动。

## 功能截图

### 技能商店

技能商店集成了 [skills.sh](https://skills.sh/) 生态系统，提供 500+ 社区技能：

- 浏览和搜索技能
- 按分类筛选（工具、数据、网络、自动化等）
- 一键安装到本地
- 支持技能翻译为中文

### 编辑器

Monaco Editor 支持：
- 实时编辑 SKILL.md / MEMORY.md 文件
- 语法高亮（Markdown、Python、JSON 等）
- 一键翻译技能文档为中文
- Ctrl+S 快捷保存

## 项目结构

```
vibeworker/
├── backend/                # FastAPI + LangChain/LangGraph
│   ├── app.py              # 入口文件
│   ├── config.py           # 配置管理
│   ├── store/              # 技能商店模块
│   │   ├── __init__.py     # SkillsStore 核心逻辑
│   │   └── models.py       # Pydantic 模型
│   ├── memory/             # 记忆存储
│   ├── sessions/           # 会话记录
│   ├── skills/             # Agent Skills
│   ├── workspace/          # System Prompts
│   ├── tools/              # Core Tools
│   ├── graph/              # Agent 编排
│   ├── knowledge/          # RAG 知识库
│   ├── storage/            # 索引持久化
│   └── requirements.txt
├── frontend/               # Next.js 14+
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   │   ├── chat/       # 对话面板
│   │   │   ├── sidebar/    # 侧边栏导航
│   │   │   ├── editor/     # Monaco 编辑器
│   │   │   ├── store/      # 技能商店组件
│   │   │   ├── settings/   # 设置弹窗
│   │   │   └── ui/         # Shadcn 基础组件
│   │   └── lib/
│   │       └── api.ts      # API 客户端
│   └── package.json
├── scripts/                # CLI 工具
│   ├── skills.sh           # Linux/macOS 技能管理脚本
│   └── skills.bat          # Windows 技能管理脚本
└── README.md
```

## CLI 工具

提供命令行工具管理技能：

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

## API 接口

### 核心接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/chat` | POST | 对话接口（支持 SSE 流式） |
| `/api/sessions` | GET/POST/DELETE | 会话管理 |
| `/api/files` | GET/POST | 文件读写 |
| `/api/skills` | GET/DELETE | 技能管理 |
| `/api/settings` | GET/PUT | 配置管理 |

### 技能商店接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/store/skills` | GET | 获取远程技能列表 |
| `/api/store/search` | GET | 搜索技能 |
| `/api/store/skills/{name}` | GET | 获取技能详情 |
| `/api/store/install` | POST | 安装技能 |
| `/api/translate` | POST | 翻译内容为中文 |

## 环境变量

在 `backend/.env` 中配置：

```env
LLM_API_KEY=your_api_key
LLM_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=4096

EMBEDDING_API_KEY=your_api_key
EMBEDDING_API_BASE=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
```

## License

MIT
