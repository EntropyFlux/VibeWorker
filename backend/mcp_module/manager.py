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
        # 存储每个 server 的连接状态：{ session, exit_stack, tools, lc_tools, status, error }
        self._lock = asyncio.Lock()
        # 后台初始化任务引用（需持有引用，防止被 GC 回收）
        self._init_task: asyncio.Task | None = None

    def start_background_init(self) -> None:
        """非阻塞启动 MCP 初始化，立即返回，不阻塞主服务器启动。

        在事件循环中创建后台 Task，并行连接所有启用的 MCP 服务器。
        初始化期间 get_all_mcp_tools() 会随连接完成逐步返回更多工具，
        单个服务器失败只影响该服务器，不影响其他服务器或主服务。
        """
        self._init_task = asyncio.create_task(
            self._background_initialize(),
            name="mcp-background-init",
        )

    async def _background_initialize(self) -> None:
        """后台并行连接所有启用的 MCP 服务器。

        使用 asyncio.gather 并行发起连接，各服务器相互隔离：
        任意一个挂起或失败都不会影响其他服务器的连接流程。
        """
        config = get_active_config()
        servers = config.get("servers", {})
        enabled = [name for name, cfg in servers.items() if cfg.get("enabled", True)]
        if not enabled:
            return

        logger.info(f"MCP 后台初始化：并行连接 {len(enabled)} 个服务器...")
        # return_exceptions=True 确保单个失败不会中断其他并发连接
        await asyncio.gather(
            *[self._safe_connect(name) for name in enabled],
            return_exceptions=True,
        )
        connected = sum(
            1 for n in enabled
            if self._connections.get(n, {}).get("status") == STATUS_CONNECTED
        )
        logger.info(f"MCP 后台初始化完成：{connected}/{len(enabled)} 个服务器已连接")

    async def _safe_connect(self, name: str) -> None:
        """带完整错误捕获的单服务器连接，供 gather 并行调用。"""
        try:
            await self.connect_server(name)
        except Exception as e:
            logger.error(f"MCP server '{name}' 连接失败（已跳过）: {e}")

    async def initialize(self) -> None:
        """串行连接所有启用的 MCP 服务器（供 API 手动触发使用）。"""
        config = get_active_config()
        servers = config.get("servers", {})
        for name, srv_config in servers.items():
            if srv_config.get("enabled", True):
                await self._safe_connect(name)

    async def shutdown(self) -> None:
        """断开所有 MCP 服务器，并取消尚未完成的后台初始化任务。"""
        # 如果后台初始化还在进行，先取消它，避免 shutdown 与 connect 并发冲突
        if self._init_task and not self._init_task.done():
            self._init_task.cancel()
            try:
                await self._init_task
            except asyncio.CancelledError:
                logger.info("MCP 后台初始化任务已取消")

        names = list(self._connections.keys())
        for name in names:
            try:
                await self.disconnect_server(name)
            except Exception as e:
                logger.warning(f"Error disconnecting MCP server '{name}': {e}")

    async def connect_server(self, name: str) -> None:
        """Connect to a specific MCP server by name.

        安全修复：使用 per-server 锁替代全局锁，防止并发连接同一服务器导致资源泄漏，
        同时允许不同服务器并行连接。
        """
        # 获取或创建该服务器专用的锁
        async with self._lock:
            if not hasattr(self, "_server_locks"):
                self._server_locks: dict[str, asyncio.Lock] = {}
            if name not in self._server_locks:
                self._server_locks[name] = asyncio.Lock()
            server_lock = self._server_locks[name]

        # 使用服务器专用锁保护整个连接过程
        async with server_lock:
            await self._connect_server_impl(name)

    async def _connect_server_impl(self, name: str) -> None:
        """实际的连接实现（必须在 server_lock 保护下调用）。"""
        # 如果已连接，先断开
        async with self._lock:
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

        exit_stack = AsyncExitStack()
        try:
            transport = srv_config.get("transport", "stdio")
            # stdio 类型进程可能因环境问题挂起，SSE 类型可能因网络延迟挂起，
            # 超时时间根据传输方式区分：stdio 默认 15s，SSE 默认 10s
            connect_timeout = 15.0 if transport == "stdio" else 10.0

            if transport == "stdio":
                session = await self._connect_stdio(name, srv_config, exit_stack)
            elif transport == "sse":
                session = await self._connect_sse(name, srv_config, exit_stack)
            else:
                raise ValueError(f"Unknown transport: {transport}")

            # Initialize the session（加超时保护：防止 MCP 进程挂起导致整个启动阻塞）
            try:
                await asyncio.wait_for(session.initialize(), timeout=connect_timeout)
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"MCP server '{name}' 握手超时（{connect_timeout:.0f}s），"
                    "可能是进程挂起或网络不通，已跳过此服务器"
                )

            # Discover tools（同样加超时：防止 list_tools 阶段挂起）
            try:
                tools_result = await asyncio.wait_for(
                    session.list_tools(), timeout=connect_timeout
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"MCP server '{name}' 工具列表获取超时（{connect_timeout:.0f}s），已跳过"
                )
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
            # 安全修复：连接失败时必须关闭 exit_stack，防止资源泄漏
            # exit_stack 可能已经注册了 stdio 子进程或 SSE HTTP 连接
            try:
                await exit_stack.aclose()
            except Exception as close_err:
                logger.warning(f"Error closing exit_stack for '{name}': {close_err}")

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
