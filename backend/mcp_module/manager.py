"""MCPManager - manages MCP server connections and tool discovery.

Handles the lifecycle of MCP server connections (stdio and SSE transports),
discovers tools from connected servers, and wraps them as LangChain tools.
"""
import asyncio
import logging
from contextlib import AsyncExitStack
from typing import Any

from langchain_core.tools import StructuredTool

from mcp_module.config import get_active_config, get_server

logger = logging.getLogger(__name__)

# Connection status constants
STATUS_DISCONNECTED = "disconnected"
STATUS_CONNECTING = "connecting"
STATUS_CONNECTED = "connected"
STATUS_ERROR = "error"


class MCPManager:
    """Manage all MCP server connections and their tools."""

    def __init__(self) -> None:
        self._connections: dict[str, dict[str, Any]] = {}
        # Stores per-server: { session, exit_stack, tools, lc_tools, status, error }
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Connect to all enabled MCP servers on startup."""
        config = get_active_config()
        servers = config.get("servers", {})
        for name, srv_config in servers.items():
            if srv_config.get("enabled", True):
                try:
                    await self.connect_server(name)
                except Exception as e:
                    logger.error(f"Failed to connect MCP server '{name}': {e}")

    async def shutdown(self) -> None:
        """Disconnect all MCP servers gracefully."""
        names = list(self._connections.keys())
        for name in names:
            try:
                await self.disconnect_server(name)
            except Exception as e:
                logger.warning(f"Error disconnecting MCP server '{name}': {e}")

    async def connect_server(self, name: str) -> None:
        """Connect to a specific MCP server by name."""
        async with self._lock:
            # If already connected, disconnect first
            if name in self._connections and self._connections[name]["status"] == STATUS_CONNECTED:
                await self._disconnect_server_unlocked(name)

            srv_config = get_server(name)
            if not srv_config:
                raise ValueError(f"MCP server '{name}' not found in config")

            self._connections[name] = {
                "session": None,
                "exit_stack": None,
                "tools": [],
                "lc_tools": [],
                "status": STATUS_CONNECTING,
                "error": None,
            }

        try:
            transport = srv_config.get("transport", "stdio")
            exit_stack = AsyncExitStack()

            if transport == "stdio":
                session = await self._connect_stdio(name, srv_config, exit_stack)
            elif transport == "sse":
                session = await self._connect_sse(name, srv_config, exit_stack)
            else:
                raise ValueError(f"Unknown transport: {transport}")

            # Initialize the session
            await session.initialize()

            # Discover tools
            tools_result = await session.list_tools()
            mcp_tools = tools_result.tools if hasattr(tools_result, "tools") else []

            # Wrap as LangChain tools
            from mcp_module.tool_wrapper import mcp_tools_to_langchain
            lc_tools = mcp_tools_to_langchain(name, mcp_tools, session)

            async with self._lock:
                self._connections[name] = {
                    "session": session,
                    "exit_stack": exit_stack,
                    "tools": mcp_tools,
                    "lc_tools": lc_tools,
                    "status": STATUS_CONNECTED,
                    "error": None,
                }

            logger.info(
                f"MCP server '{name}' connected ({transport}), "
                f"discovered {len(mcp_tools)} tools"
            )

        except Exception as e:
            logger.error(f"MCP server '{name}' connection failed: {e}")
            async with self._lock:
                self._connections[name] = {
                    "session": None,
                    "exit_stack": None,
                    "tools": [],
                    "lc_tools": [],
                    "status": STATUS_ERROR,
                    "error": str(e),
                }
            raise

    async def _connect_stdio(
        self, name: str, srv_config: dict, exit_stack: AsyncExitStack
    ) -> Any:
        """Connect via stdio transport (local process)."""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        command = srv_config.get("command", "")
        args = srv_config.get("args", [])
        env = srv_config.get("env", None)

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=env,
        )

        stdio_transport = await exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read_stream, write_stream = stdio_transport
        session = await exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        return session

    async def _connect_sse(
        self, name: str, srv_config: dict, exit_stack: AsyncExitStack
    ) -> Any:
        """Connect via SSE transport (remote HTTP)."""
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        url = srv_config.get("url", "")
        headers = srv_config.get("headers", {})

        sse_transport = await exit_stack.enter_async_context(
            sse_client(url=url, headers=headers)
        )
        read_stream, write_stream = sse_transport
        session = await exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        return session

    async def disconnect_server(self, name: str) -> None:
        """Disconnect a specific MCP server."""
        async with self._lock:
            await self._disconnect_server_unlocked(name)

    async def _disconnect_server_unlocked(self, name: str) -> None:
        """Internal disconnect (must be called under lock)."""
        conn = self._connections.get(name)
        if not conn:
            return
        exit_stack = conn.get("exit_stack")
        if exit_stack:
            try:
                await exit_stack.aclose()
            except Exception as e:
                logger.warning(f"Error closing MCP server '{name}': {e}")
        self._connections[name] = {
            "session": None,
            "exit_stack": None,
            "tools": [],
            "lc_tools": [],
            "status": STATUS_DISCONNECTED,
            "error": None,
        }

    def get_all_mcp_tools(self) -> list[StructuredTool]:
        """Return all LangChain tools from all connected MCP servers."""
        tools = []
        for conn in self._connections.values():
            if conn["status"] == STATUS_CONNECTED:
                tools.extend(conn["lc_tools"])
        return tools

    def get_server_status(self) -> dict[str, dict[str, Any]]:
        """Return status info for all known servers."""
        config = get_active_config()
        result = {}
        for name, srv_config in config.get("servers", {}).items():
            conn = self._connections.get(name, {})
            status = conn.get("status", STATUS_DISCONNECTED)
            tools = conn.get("tools", [])
            result[name] = {
                **srv_config,
                "status": status,
                "tools_count": len(tools),
                "error": conn.get("error"),
            }
        return result

    def get_server_tools(self, name: str) -> list[dict[str, str]]:
        """Return tool list for a specific server."""
        conn = self._connections.get(name, {})
        tools = conn.get("tools", [])
        return [
            {
                "name": t.name,
                "description": t.description or "",
            }
            for t in tools
        ]
