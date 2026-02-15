"""Memory Write Tool - Write memories to MEMORY.md or daily logs."""
import logging

from langchain_core.tools import tool
from memory_manager import memory_manager, VALID_CATEGORIES, CATEGORY_LABELS

logger = logging.getLogger(__name__)


@tool
def memory_write(content: str, category: str = "general", write_to: str = "memory") -> str:
    """Write a memory entry to long-term memory or daily log.

    Use this tool to record important information that should persist across sessions.

    Args:
        content: The information to remember. Be concise but specific.
        category: Category for the entry. One of:
            - "preferences" (用户偏好): user preferences, habits, likes/dislikes
            - "facts" (重要事实): factual information about user/project/environment
            - "tasks" (任务备忘): task notes, TODOs, reminders
            - "reflections" (反思日志): lessons learned, insights
            - "general" (通用记忆): anything else worth remembering
        write_to: Where to write. One of:
            - "memory" → writes to MEMORY.md (long-term, persistent)
            - "daily" → writes to today's daily log (short-term, date-specific)

    Returns:
        Confirmation message with the entry details.
    """
    if not content or not content.strip():
        return "❌ Error: Content cannot be empty."

    content = content.strip()

    if category not in VALID_CATEGORIES:
        return f"❌ Error: Invalid category '{category}'. Valid: {', '.join(VALID_CATEGORIES)}"

    try:
        if write_to == "daily":
            memory_manager.append_daily_log(content)
            return f"✅ 已写入今日日志: {content[:100]}..."
        elif write_to == "memory":
            entry = memory_manager.add_entry(content, category)
            cat_label = CATEGORY_LABELS.get(category, category)
            return (
                f"✅ 已写入长期记忆 [{cat_label}]: {content[:100]}...\n"
                f"Entry ID: {entry['entry_id']}"
            )
        else:
            return f"❌ Error: Invalid write_to '{write_to}'. Use 'memory' or 'daily'."
    except Exception as e:
        logger.error(f"Memory write failed: {e}")
        return f"❌ Error writing memory: {str(e)}"


def create_memory_write_tool():
    """Factory function to create the memory_write tool."""
    return memory_write
