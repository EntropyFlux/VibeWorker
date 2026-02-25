"""MCP Server configuration management.

Handles loading and saving mcp_servers.json from user data directory,
and merges external configurations (like Claude Desktop and Claude Code).
"""
import json
import logging
import os
import platform
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_config_file() -> Path:
    """Get mcp_servers.json path from data directory."""
    from config import settings
    return settings.get_data_path() / "mcp_servers.json"


def _get_claude_desktop_config_path() -> Path | None:
    """Locate Claude Desktop config file based on OS."""
    system = platform.system()
    if system == "Windows":
        appdata = os.getenv("APPDATA")
        if appdata:
            path = Path(appdata) / "Claude" / "claude_desktop_config.json"
            if path.exists():
                return path
    elif system == "Darwin":
        path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        if path.exists():
            return path
    return None


def _get_claude_code_config_path() -> Path | None:
    """Locate Claude Code config file."""
    path = Path.home() / ".claude.json"
    if path.exists():
        return path
    return None


def load_config() -> dict[str, Any]:
    """Load MCP server configurations from mcp_servers.json."""
    config_file = _get_config_file()
    if not config_file.exists():
        return {"servers": {}}
    try:
        data = json.loads(config_file.read_text(encoding="utf-8-sig"))
        if "servers" not in data:
            data["servers"] = {}
        return data
    except Exception as e:
        logger.error(f"Failed to load MCP config: {e}")
        return {"servers": {}}


def get_active_config() -> dict[str, Any]:
    """Load and merge local MCP servers with Claude Desktop/Code configs."""
    local_config = load_config()
    merged_servers = {}
    
    # 1. Load Claude configs first so local config can override them
    claude_paths = {
        "claude_desktop": _get_claude_desktop_config_path(),
        "claude_code": _get_claude_code_config_path(),
    }
    
    for source, path in claude_paths.items():
        if path:
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                mcp_servers_to_add = {}
                
                if source == "claude_code":
                    # Global servers
                    for k, v in data.get("mcpServers", {}).items():
                        mcp_servers_to_add[k] = v
                    # Project-specific servers
                    for proj_path, proj_data in data.get("projects", {}).items():
                        proj_name = Path(proj_path).name if proj_path else "unknown"
                        for k, v in proj_data.get("mcpServers", {}).items():
                            server_name = f"{k} [{proj_name}]"
                            mcp_servers_to_add[server_name] = v
                else:
                    mcp_servers_to_add = data.get("mcpServers", {})
                    
                for name, srv_config in mcp_servers_to_add.items():
                    # Adapt to OpenSRE format
                    transport = "sse" if "url" in srv_config else "stdio"
                    merged_servers[name] = {
                        "command": srv_config.get("command", ""),
                        "args": srv_config.get("args", []),
                        "env": srv_config.get("env", {}),
                        "url": srv_config.get("url", ""),
                        "headers": srv_config.get("headers", {}),
                        "transport": transport,
                        "enabled": True,
                        "description": f"Imported from {source.replace('_', ' ').title()}",
                        "source": source
                    }
            except Exception as e:
                logger.warning(f"Failed to load {source} config from {path}: {e}")
                
    # 2. Add/Override with local config
    for name, srv_config in local_config.get("servers", {}).items():
        merged_servers[name] = srv_config
        
    return {"servers": merged_servers}


def save_config(data: dict[str, Any]) -> None:
    """Save MCP server configurations to mcp_servers.json."""
    config_file = _get_config_file()
    config_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_server(name: str) -> dict[str, Any] | None:
    """Get a single server config by name."""
    config = get_active_config()
    return config["servers"].get(name)


def set_server(name: str, server_config: dict[str, Any]) -> None:
    """Add or update a server config in local file."""
    config = load_config()
    config["servers"][name] = server_config
    save_config(config)


def delete_server(name: str) -> bool:
    """Delete a server config from local file. Returns True if found and deleted."""
    config = load_config()
    if name not in config["servers"]:
        return False
    del config["servers"][name]
    save_config(config)
    return True
