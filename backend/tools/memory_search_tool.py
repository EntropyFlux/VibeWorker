"""Memory Search Tool - Search across all memory files using keyword or vector search.

记忆系统 v2：
- 使用新的 memory.search 模块
- 支持重要性 × 时间衰减排序
- 支持 procedural 分类检索
"""
import logging
from typing import Optional

from langchain_core.tools import tool
from config import settings

logger = logging.getLogger(__name__)


@tool
def memory_search(query: str, top_k: int = 5, use_decay: bool = True, category: Optional[str] = None) -> str:
    """Search across all memory files (memory.json + daily logs).

    Use this tool to find past memories, user preferences, task notes,
    procedural knowledge (tool usage experiences), or any previously recorded information.

    Args:
        query: Search query describing what you're looking for.
        top_k: Maximum number of results to return (default 5).
        use_decay: Whether to apply time decay to relevance scores (default True).
            When True, recent memories rank higher than older ones.
        category: Optional category filter. One of:
            - "preferences": user preferences
            - "facts": important facts
            - "tasks": task notes
            - "reflections": lessons learned
            - "procedural": tool usage experiences
            - "general": other information

    Returns:
        Matching memory entries with their sources and relevance scores.
    """
    if not query or not query.strip():
        return "❌ Error: Query cannot be empty."

    try:
        from memory.search import search_memories

        results = search_memories(
            query=query,
            top_k=top_k,
            use_decay=use_decay,
            category=category,
        )

        if not results:
            return f"未找到与 '{query}' 相关的记忆。"

        formatted = []
        for r in results:
            source = r.get("source", "unknown")
            score = r.get("score", 0)
            salience = r.get("salience", 0.5)
            content = r.get("content", "")[:300]
            cat = r.get("category", "")

            # 构建结果行
            cat_str = f" [{cat}]" if cat else ""
            salience_str = f" ⭐" if salience >= 0.8 else ""
            formatted.append(
                f"📝 [{source}]{cat_str}{salience_str} (相关度: {score:.2f})\n{content}"
            )

        return f"找到 {len(results)} 条相关记忆:\n\n" + "\n\n---\n\n".join(formatted)

    except Exception as e:
        logger.error(f"Memory search failed: {e}")
        return f"❌ 搜索失败: {str(e)}"


def rebuild_memory_index() -> str:
    """Force rebuild the memory search index."""
    try:
        from memory.search import rebuild_memory_index as _rebuild
        return _rebuild()
    except Exception as e:
        logger.error(f"Rebuild memory index failed: {e}")
        return f"❌ 重建索引失败: {str(e)}"


def create_memory_search_tool():
    """Factory function to create the memory_search tool."""
    return memory_search
