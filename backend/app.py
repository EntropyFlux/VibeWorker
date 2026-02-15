"""VibeWorker Backend - FastAPI Application Entry Point

Run with: python app.py
Server starts at: http://localhost:8088
"""
import json
import logging
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

from config import settings, PROJECT_ROOT
from sessions_manager import session_manager
from graph.agent import run_agent
from tools.rag_tool import rebuild_index

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vibeworker")

# ============================================
# FastAPI Application
# ============================================
app = FastAPI(
    title="VibeWorker API",
    description="VibeWorker - Your Local AI Digital Worker with Real Memory",
    version="0.1.0",
)

# CORS - Allow frontend (Next.js dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# Startup
# ============================================
@app.on_event("startup")
async def startup_event():
    """Initialize directories and resources on startup."""
    settings.ensure_dirs()
    logger.info("VibeWorker Backend started on port %d", settings.port)
    logger.info("Project root: %s", PROJECT_ROOT)


# ============================================
# Request/Response Models
# ============================================
class ChatRequest(BaseModel):
    message: str
    session_id: str = "main_session"
    stream: bool = True


class FileWriteRequest(BaseModel):
    path: str
    content: str


class SessionCreateRequest(BaseModel):
    session_id: Optional[str] = None


# ============================================
# API Routes: Chat
# ============================================
@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Send a user message and get Agent response.
    Supports SSE (Server-Sent Events) streaming.
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Ensure session exists
    session_manager.create_session(request.session_id)

    # Save user message
    session_manager.save_message(request.session_id, "user", request.message)

    # Get session history (exclude the message we just saved, it's already in the input)
    history = session_manager.get_session(request.session_id)[:-1]

    if request.stream:
        return StreamingResponse(
            _stream_agent_response(request.message, history, request.session_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        # Non-streaming mode
        full_response = ""
        tool_calls_log = []
        async for event in run_agent(request.message, history, stream=False):
            if event["type"] == "message":
                full_response = event["content"]
            elif event["type"] == "tool_start":
                tool_calls_log.append({
                    "tool": event["tool"],
                    "input": event.get("input", ""),
                })
            elif event["type"] == "tool_end":
                for tc in tool_calls_log:
                    if tc["tool"] == event["tool"] and "output" not in tc:
                        tc["output"] = event.get("output", "")
                        break

        # Save assistant response
        session_manager.save_message(
            request.session_id, "assistant", full_response,
            tool_calls=tool_calls_log if tool_calls_log else None,
        )

        return {
            "response": full_response,
            "session_id": request.session_id,
            "tool_calls": tool_calls_log,
        }


async def _stream_agent_response(message: str, history: list, session_id: str):
    """Generator for SSE streaming."""
    full_response = ""
    tool_calls_log = []

    try:
        async for event in run_agent(message, history, stream=True):
            event_type = event.get("type", "")

            if event_type == "token":
                content = event.get("content", "")
                full_response += content
                sse_data = json.dumps({"type": "token", "content": content}, ensure_ascii=False)
                yield f"data: {sse_data}\n\n"

            elif event_type == "tool_start":
                tool_calls_log.append({
                    "tool": event["tool"],
                    "input": event.get("input", ""),
                })
                sse_data = json.dumps({
                    "type": "tool_start",
                    "tool": event["tool"],
                    "input": event.get("input", ""),
                }, ensure_ascii=False)
                yield f"data: {sse_data}\n\n"

            elif event_type == "tool_end":
                for tc in tool_calls_log:
                    if tc["tool"] == event["tool"] and "output" not in tc:
                        tc["output"] = event.get("output", "")
                        break
                sse_data = json.dumps({
                    "type": "tool_end",
                    "tool": event["tool"],
                    "output": event.get("output", "")[:1000],
                }, ensure_ascii=False)
                yield f"data: {sse_data}\n\n"

            elif event_type == "done":
                # Save assistant response to session
                if full_response:
                    session_manager.save_message(
                        session_id, "assistant", full_response,
                        tool_calls=tool_calls_log if tool_calls_log else None,
                    )
                sse_data = json.dumps({"type": "done"}, ensure_ascii=False)
                yield f"data: {sse_data}\n\n"

    except Exception as e:
        logger.error(f"Error in agent stream: {e}", exc_info=True)
        error_data = json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False)
        yield f"data: {error_data}\n\n"


# ============================================
# API Routes: File Management
# ============================================
@app.get("/api/files")
async def read_file(path: str = Query(..., description="Relative file path")):
    """Read the content of a file within the project."""
    file_path = (PROJECT_ROOT / path).resolve()

    # Security check
    try:
        file_path.relative_to(PROJECT_ROOT)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: path outside project")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not file_path.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    try:
        content = file_path.read_text(encoding="utf-8")
        return {"path": path, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}")


@app.post("/api/files")
async def write_file(request: FileWriteRequest):
    """Save content to a file within the project (for Memory/Skill editing)."""
    file_path = (PROJECT_ROOT / request.path).resolve()

    # Security check
    try:
        file_path.relative_to(PROJECT_ROOT)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: path outside project")

    # Only allow editing certain directories
    allowed_prefixes = ["memory", "workspace", "skills", "knowledge"]
    if not any(request.path.startswith(prefix) for prefix in allowed_prefixes):
        raise HTTPException(
            status_code=403,
            detail="Can only edit files in memory/, workspace/, skills/, or knowledge/ directories",
        )

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(request.content, encoding="utf-8")
        return {"status": "ok", "path": request.path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error writing file: {e}")


@app.get("/api/files/tree")
async def file_tree(root: str = Query("", description="Root directory to list")):
    """Get file tree for the sidebar file explorer."""
    base = PROJECT_ROOT / root if root else PROJECT_ROOT
    base = base.resolve()

    try:
        base.relative_to(PROJECT_ROOT)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not base.exists():
        raise HTTPException(status_code=404, detail="Directory not found")

    def _build_tree(dir_path: Path, depth: int = 0, max_depth: int = 3) -> list:
        if depth > max_depth:
            return []
        items = []
        try:
            for entry in sorted(dir_path.iterdir()):
                # Skip hidden files and __pycache__
                if entry.name.startswith(".") or entry.name == "__pycache__":
                    continue
                rel = str(entry.relative_to(PROJECT_ROOT)).replace("\\", "/")
                if entry.is_dir():
                    children = _build_tree(entry, depth + 1, max_depth)
                    items.append({
                        "name": entry.name,
                        "path": rel,
                        "type": "directory",
                        "children": children,
                    })
                else:
                    items.append({
                        "name": entry.name,
                        "path": rel,
                        "type": "file",
                        "size": entry.stat().st_size,
                    })
        except PermissionError:
            pass
        return items

    return _build_tree(base)


# ============================================
# API Routes: Session Management
# ============================================
@app.get("/api/sessions")
async def list_sessions():
    """Get all historical session list."""
    sessions = session_manager.list_sessions()
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get messages for a specific session."""
    messages = session_manager.get_session(session_id)
    return {"session_id": session_id, "messages": messages}


@app.post("/api/sessions")
async def create_session(request: SessionCreateRequest):
    """Create a new session."""
    session_id = session_manager.create_session(request.session_id)
    return {"session_id": session_id}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    success = session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "ok"}


# ============================================
# API Routes: Skills Management
# ============================================
@app.get("/api/skills")
async def list_skills():
    """List all available skills."""
    from prompt_builder import generate_skills_snapshot, _parse_skill_frontmatter

    skills = []
    if settings.skills_dir.exists():
        for skill_dir in sorted(settings.skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            name, description = _parse_skill_frontmatter(skill_md)
            if not name:
                name = skill_dir.name
            rel_path = str(skill_md.relative_to(PROJECT_ROOT)).replace("\\", "/")
            skills.append({
                "name": name,
                "description": description,
                "location": rel_path,
            })

    return {"skills": skills}


@app.delete("/api/skills/{skill_name}")
async def delete_skill(skill_name: str):
    """Delete a skill by removing its folder."""
    import shutil

    # Sanitize skill name
    safe_name = "".join(c for c in skill_name if c.isalnum() or c in "_-")
    skill_dir = settings.skills_dir / safe_name

    if not skill_dir.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    # Security: ensure it's within skills directory
    try:
        skill_dir.resolve().relative_to(settings.skills_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        shutil.rmtree(skill_dir)
        return {"status": "ok", "deleted": skill_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting skill: {e}")


# ============================================
# API Routes: Skills Store
# ============================================
from store import SkillsStore
from store.models import InstallRequest, RemoteSkill

# Initialize skills store - integrates with skills.sh ecosystem
skills_store = SkillsStore(
    skills_dir=settings.skills_dir,
    cache_ttl=settings.store_cache_ttl,
)


@app.get("/api/store/skills")
async def list_store_skills(
    category: Optional[str] = Query(None, description="Filter by category"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
):
    """List available skills from remote registry."""
    try:
        result = await skills_store.list_remote_skills(
            category=category,
            page=page,
            page_size=page_size,
        )
        return result.model_dump()
    except Exception as e:
        logger.error(f"Failed to list store skills: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to fetch skills: {e}")


@app.get("/api/store/search")
async def search_store_skills(q: str = Query(..., min_length=1, description="Search query")):
    """Search skills by name, description, or tags."""
    try:
        results = await skills_store.search_skills(q)
        return {"query": q, "results": [r.model_dump() for r in results]}
    except Exception as e:
        logger.error(f"Failed to search skills: {e}")
        raise HTTPException(status_code=503, detail=f"Search failed: {e}")


@app.get("/api/store/skills/{skill_name}")
async def get_store_skill_detail(skill_name: str):
    """Get detailed information about a specific skill."""
    try:
        detail = await skills_store.get_skill_detail(skill_name)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
        return detail.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get skill detail: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to fetch skill detail: {e}")


@app.post("/api/store/install")
async def install_store_skill(request: InstallRequest):
    """Install a skill from remote registry."""
    try:
        result = await skills_store.install_skill(
            name=request.skill_name,
            version=request.version,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to install skill: {e}")
        raise HTTPException(status_code=500, detail=f"Installation failed: {e}")


@app.post("/api/skills/{skill_name}/update")
async def update_installed_skill(skill_name: str):
    """Update an installed skill to the latest version."""
    try:
        result = await skills_store.update_skill(skill_name)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update skill: {e}")
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")


@app.get("/api/store/categories")
async def get_store_categories():
    """Get available skill categories."""
    return {"categories": skills_store.get_categories()}


# ============================================
# API Routes: Knowledge Base
# ============================================
@app.post("/api/knowledge/rebuild")
async def rebuild_knowledge_base():
    """Force rebuild the RAG knowledge base index."""
    result = rebuild_index()
    return {"status": result}


# ============================================
# Translation API
# ============================================
class TranslateRequest(BaseModel):
    content: str
    target_language: str = "zh-CN"


@app.post("/api/translate")
async def translate_content(request: TranslateRequest):
    """Translate skill description content to target language using LLM."""
    from langchain_openai import ChatOpenAI

    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    try:
        # Use translation model config if set, otherwise fall back to main LLM config
        api_key = settings.translate_api_key or settings.llm_api_key
        api_base = settings.translate_api_base or settings.llm_api_base
        model = settings.translate_model or settings.llm_model

        llm = ChatOpenAI(
            api_key=api_key,
            base_url=api_base,
            model=model,
            temperature=0.2,
        )

        # Precise translation prompt - only translate descriptions, keep code intact
        prompt = f"""你是一个专业的技术文档翻译专家。请将以下 SKILL.md 文件翻译成中文。

**严格遵守以下规则：**

1. **必须翻译的内容：**
   - YAML frontmatter 中的 `description` 字段值
   - 标题（# ## ### 等）
   - 段落描述文字
   - 列表项中的说明文字
   - 注释文字

2. **绝对不能翻译的内容：**
   - YAML frontmatter 中的 `name` 字段（保持英文）
   - 代码块（``` 包裹的内容）内的所有代码
   - 行内代码（`包裹的内容`）
   - URL 链接
   - 文件路径
   - 命令行指令
   - 变量名、函数名、API 名称
   - JSON/YAML 结构中的 key 名

3. **格式要求：**
   - 保持原有的 Markdown 格式结构不变
   - 保持代码块的语言标识（如 ```python）
   - 保持缩进和空行

原文：
{request.content}

请直接输出翻译后的完整内容，不要添加任何解释："""

        response = await llm.ainvoke(prompt)
        translated = response.content

        # Clean up potential markdown code block wrapper from LLM response
        if translated.startswith("```") and translated.endswith("```"):
            lines = translated.split("\n")
            if len(lines) > 2:
                translated = "\n".join(lines[1:-1])

        return {
            "status": "ok",
            "translated": translated,
            "source_language": "auto",
            "target_language": request.target_language,
            "model": model,
        }
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Translation failed: {e}")


# ============================================
# Health Check
# ============================================
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": "0.1.0",
        "model": settings.llm_model,
    }


# ============================================
# Settings API
# ============================================
class SettingsUpdateRequest(BaseModel):
    openai_api_key: Optional[str] = None
    openai_api_base: Optional[str] = None
    llm_model: Optional[str] = None
    llm_temperature: Optional[float] = None
    llm_max_tokens: Optional[int] = None
    embedding_api_key: Optional[str] = None
    embedding_api_base: Optional[str] = None
    embedding_model: Optional[str] = None
    # Translation model (optional, falls back to main LLM if not set)
    translate_api_key: Optional[str] = None
    translate_api_base: Optional[str] = None
    translate_model: Optional[str] = None


def _read_env_file() -> dict:
    """Read .env file and parse into dict."""
    env_path = PROJECT_ROOT / ".env"
    result = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                result[key.strip()] = value.strip()
    return result


def _write_env_file(env_dict: dict) -> None:
    """Write dict back to .env file, preserving comments and structure."""
    env_path = PROJECT_ROOT / ".env"
    lines = []
    if env_path.exists():
        original_lines = env_path.read_text(encoding="utf-8").splitlines()
        updated_keys = set()
        for line in original_lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in env_dict:
                    lines.append(f"{key}={env_dict[key]}")
                    updated_keys.add(key)
                else:
                    lines.append(line)
            else:
                lines.append(line)
        # Add any new keys not already in file
        for key, value in env_dict.items():
            if key not in updated_keys:
                lines.append(f"{key}={value}")
    else:
        for key, value in env_dict.items():
            lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@app.get("/api/settings")
async def get_settings():
    """Get current model configuration from .env."""
    env = _read_env_file()
    return {
        "openai_api_key": env.get("OPENAI_API_KEY", ""),
        "openai_api_base": env.get("OPENAI_API_BASE", ""),
        "llm_model": env.get("LLM_MODEL", ""),
        "llm_temperature": float(env.get("LLM_TEMPERATURE", "0.7")),
        "llm_max_tokens": int(env.get("LLM_MAX_TOKENS", "4096")),
        "embedding_api_key": env.get("EMBEDDING_API_KEY", ""),
        "embedding_api_base": env.get("EMBEDDING_API_BASE", ""),
        "embedding_model": env.get("EMBEDDING_MODEL", ""),
        # Translation model config
        "translate_api_key": env.get("TRANSLATE_API_KEY", ""),
        "translate_api_base": env.get("TRANSLATE_API_BASE", ""),
        "translate_model": env.get("TRANSLATE_MODEL", ""),
    }


@app.put("/api/settings")
async def update_settings(request: SettingsUpdateRequest):
    """Update model configuration in .env file."""
    env = _read_env_file()
    update_map = {
        "OPENAI_API_KEY": request.openai_api_key,
        "OPENAI_API_BASE": request.openai_api_base,
        "LLM_MODEL": request.llm_model,
        "LLM_TEMPERATURE": str(request.llm_temperature) if request.llm_temperature is not None else None,
        "LLM_MAX_TOKENS": str(request.llm_max_tokens) if request.llm_max_tokens is not None else None,
        "EMBEDDING_API_KEY": request.embedding_api_key,
        "EMBEDDING_API_BASE": request.embedding_api_base,
        "EMBEDDING_MODEL": request.embedding_model,
        # Translation model
        "TRANSLATE_API_KEY": request.translate_api_key,
        "TRANSLATE_API_BASE": request.translate_api_base,
        "TRANSLATE_MODEL": request.translate_model,
    }
    for env_key, value in update_map.items():
        if value is not None:
            env[env_key] = value
    _write_env_file(env)
    return {"status": "ok", "message": "Settings saved. Restart backend to apply changes."}


# ============================================
# Entry Point
# ============================================
if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info",
    )
