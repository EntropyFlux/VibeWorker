"""Core Tools Package - 7 built-in tools for VibeWorker Agent."""
from tools.terminal_tool import create_terminal_tool
from tools.python_repl_tool import create_python_repl_tool
from tools.fetch_url_tool import create_fetch_url_tool
from tools.read_file_tool import create_read_file_tool
from tools.rag_tool import create_rag_tool
from tools.memory_write_tool import create_memory_write_tool
from tools.memory_search_tool import create_memory_search_tool

__all__ = [
    "create_terminal_tool",
    "create_python_repl_tool",
    "create_fetch_url_tool",
    "create_read_file_tool",
    "create_rag_tool",
    "create_memory_write_tool",
    "create_memory_search_tool",
]


def get_all_tools() -> list:
    """Create and return all 7 core tools."""
    tools = [
        create_terminal_tool(),
        create_python_repl_tool(),
        create_fetch_url_tool(),
        create_read_file_tool(),
        create_rag_tool(),
        create_memory_write_tool(),
        create_memory_search_tool(),
    ]
    return tools
