"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
    ChevronRight,
    ChevronDown,
    Plus,
    Plug,
    PlugZap,
    Pencil,
    Trash2,
    RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    Tooltip,
    TooltipContent,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import {
    fetchMcpServers,
    addMcpServer,
    updateMcpServer,
    deleteMcpServer,
    connectMcpServer,
    disconnectMcpServer,
    fetchMcpServerTools,
    type McpServerInfo,
    type McpServerConfig,
    type McpTool,
} from "@/lib/api";
import McpServerDialog from "./McpServerDialog";

interface McpPanelProps {
    onFileOpen?: (path: string) => void;
}

const STATUS_COLORS: Record<string, string> = {
    connected: "bg-green-500",
    connecting: "bg-amber-500 animate-pulse",
    error: "bg-red-500",
    disconnected: "bg-gray-400",
};

const STATUS_LABELS: Record<string, string> = {
    connected: "已连接",
    connecting: "连接中...",
    error: "连接失败",
    disconnected: "未连接",
};

export default function McpPanel({ onFileOpen }: McpPanelProps) {
    const [servers, setServers] = useState<Record<string, McpServerInfo>>({});
    const [expandedServer, setExpandedServer] = useState<string | null>(null);
    const [serverTools, setServerTools] = useState<McpTool[]>([]);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [editingServer, setEditingServer] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    const loadServers = useCallback(async () => {
        try {
            const data = await fetchMcpServers();
            setServers(data);
        } catch {
            // Backend might not be running
        }
    }, []);

    useEffect(() => {
        loadServers();
    }, [loadServers]);

    const handleExpand = useCallback(
        async (name: string) => {
            if (expandedServer === name) {
                setExpandedServer(null);
                setServerTools([]);
            } else {
                setExpandedServer(name);
                setServerTools([]);
                try {
                    const tools = await fetchMcpServerTools(name);
                    setServerTools(tools);
                } catch {
                    // ignore
                }
            }
        },
        [expandedServer]
    );

    const handleConnect = useCallback(
        async (e: React.MouseEvent, name: string) => {
            e.stopPropagation();
            setLoading(true);
            try {
                await connectMcpServer(name);
                await loadServers();
                if (expandedServer === name) {
                    const tools = await fetchMcpServerTools(name);
                    setServerTools(tools);
                }
            } catch {
                // ignore
            } finally {
                setLoading(false);
            }
        },
        [loadServers, expandedServer]
    );

    const handleDisconnect = useCallback(
        async (e: React.MouseEvent, name: string) => {
            e.stopPropagation();
            setLoading(true);
            try {
                await disconnectMcpServer(name);
                await loadServers();
                if (expandedServer === name) {
                    setServerTools([]);
                }
            } catch {
                // ignore
            } finally {
                setLoading(false);
            }
        },
        [loadServers, expandedServer]
    );

    const handleDelete = useCallback(
        async (e: React.MouseEvent, name: string) => {
            e.stopPropagation();
            if (!confirm(`确定要删除 MCP Server「${name}」吗？`)) return;
            try {
                await deleteMcpServer(name);
                if (expandedServer === name) {
                    setExpandedServer(null);
                    setServerTools([]);
                }
                await loadServers();
            } catch {
                // ignore
            }
        },
        [loadServers, expandedServer]
    );

    const handleEdit = useCallback(
        (e: React.MouseEvent, name: string) => {
            e.stopPropagation();
            setEditingServer(name);
            setDialogOpen(true);
        },
        []
    );

    const handleAddNew = useCallback(() => {
        setEditingServer(null);
        setDialogOpen(true);
    }, []);

    const handleSave = useCallback(
        async (name: string, config: McpServerConfig) => {
            try {
                if (editingServer) {
                    await updateMcpServer(name, config);
                } else {
                    await addMcpServer(name, config);
                }
                await loadServers();
            } catch (err) {
                console.error("Failed to save MCP server:", err);
            }
        },
        [editingServer, loadServers]
    );

    const serverEntries = Object.entries(servers);
    const editConfig = editingServer ? servers[editingServer] : undefined;

    return (
        <div className="space-y-1">
            {/* Header actions */}
            <div className="flex items-center gap-1 px-2 pb-1">
                <Tooltip>
                    <TooltipTrigger asChild>
                        <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-xs"
                            onClick={handleAddNew}
                        >
                            <Plus className="w-3 h-3 mr-1" />
                            添加
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent>添加 MCP Server</TooltipContent>
                </Tooltip>
                <Tooltip>
                    <TooltipTrigger asChild>
                        <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-xs"
                            onClick={loadServers}
                        >
                            <RefreshCw className="w-3 h-3 mr-1" />
                            刷新
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent>刷新状态</TooltipContent>
                </Tooltip>
            </div>

            {/* Empty state */}
            {serverEntries.length === 0 && (
                <div className="px-3 py-8 text-center">
                    <Plug className="w-8 h-8 mx-auto mb-2 text-muted-foreground/30" />
                    <p className="text-xs text-muted-foreground">暂无 MCP Server</p>
                    <p className="text-xs text-muted-foreground/60 mt-1">
                        点击「添加」连接外部工具
                    </p>
                </div>
            )}

            {/* Server list */}
            {serverEntries.map(([name, info]) => {
                const isExpanded = expandedServer === name;
                const statusColor = STATUS_COLORS[info.status] || STATUS_COLORS.disconnected;
                const statusLabel = STATUS_LABELS[info.status] || info.status;
                const isConnected = info.status === "connected";
                const isExternal = info.source === "claude_desktop" || info.source === "claude_code";
                const externalLabel = info.source === "claude_desktop" ? "Claude Desktop" : (info.source === "claude_code" ? "Claude Code" : "");

                return (
                    <div key={name}>
                        {/* Server header */}
                        <button
                            className={`w-full text-left px-3 py-2 rounded-xl text-sm transition-all duration-150 flex items-center gap-2 group ${isExpanded
                                    ? "bg-primary/10 text-primary"
                                    : "hover:bg-accent text-foreground/70"
                                }`}
                            onClick={() => handleExpand(name)}
                        >
                            {isExpanded ? (
                                <ChevronDown className="w-3.5 h-3.5 shrink-0" />
                            ) : (
                                <ChevronRight className="w-3.5 h-3.5 shrink-0" />
                            )}
                            <div className={`w-2 h-2 rounded-full shrink-0 ${statusColor}`} />
                            <span className="flex-1 min-w-0 truncate font-medium text-xs">
                                {name}
                            </span>
                            {isExternal && (
                                <span className="text-[9px] px-1.5 py-0.5 rounded bg-accent text-muted-foreground shrink-0 border border-border/50">
                                    {externalLabel}
                                </span>
                            )}
                            {isConnected && (
                                <span className="text-[10px] text-muted-foreground/50 shrink-0">
                                    {info.tools_count}
                                </span>
                            )}
                        </button>

                        {/* Expanded content */}
                        {isExpanded && (
                            <div className="ml-3 mr-1 mt-1 space-y-1.5">
                                {/* Status info */}
                                <div className="px-2 py-1.5 text-[10px] text-muted-foreground/60 bg-muted/30 rounded-lg space-y-0.5">
                                    <div>状态: {statusLabel}</div>
                                    <div>传输: {info.transport}</div>
                                    {info.transport === "stdio" && info.command && (
                                        <div className="font-mono truncate">
                                            命令: {info.command} {info.args?.join(" ")}
                                        </div>
                                    )}
                                    {info.transport === "sse" && info.url && (
                                        <div className="font-mono truncate">URL: {info.url}</div>
                                    )}
                                    {info.description && <div>描述: {info.description}</div>}
                                    {info.error && (
                                        <div className="text-red-500 truncate">
                                            错误: {info.error}
                                        </div>
                                    )}
                                </div>

                                {/* Action buttons */}
                                <div className="flex items-center gap-1 px-1">
                                    {isConnected ? (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="h-6 px-2 text-[10px]"
                                            onClick={(e) => handleDisconnect(e, name)}
                                            disabled={loading}
                                        >
                                            <PlugZap className="w-3 h-3 mr-1" />
                                            断开
                                        </Button>
                                    ) : (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="h-6 px-2 text-[10px]"
                                            onClick={(e) => handleConnect(e, name)}
                                            disabled={loading}
                                        >
                                            <Plug className="w-3 h-3 mr-1" />
                                            连接
                                        </Button>
                                    )}
                                    {!isExternal && (
                                        <>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="h-6 px-2 text-[10px]"
                                                onClick={(e) => handleEdit(e, name)}
                                            >
                                                <Pencil className="w-3 h-3 mr-1" />
                                                编辑
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="h-6 px-2 text-[10px] text-destructive hover:text-destructive"
                                                onClick={(e) => handleDelete(e, name)}
                                            >
                                                <Trash2 className="w-3 h-3 mr-1" />
                                                删除
                                            </Button>
                                        </>
                                    )}
                                </div>

                                {/* Tools list */}
                                {isConnected && serverTools.length > 0 && (
                                    <div className="px-2 py-1 space-y-0.5">
                                        <div className="text-[10px] text-muted-foreground/50 font-semibold uppercase tracking-wider mb-1">
                                            工具列表
                                        </div>
                                        {serverTools.map((tool) => (
                                            <div
                                                key={tool.name}
                                                className="flex items-start gap-1.5 py-0.5"
                                            >
                                                <span className="text-[10px] text-muted-foreground/30 mt-0.5 shrink-0">
                                                    -
                                                </span>
                                                <div className="min-w-0">
                                                    <span className="text-[11px] font-mono text-foreground/70">
                                                        {tool.name}
                                                    </span>
                                                    {tool.description && (
                                                        <p className="text-[10px] text-muted-foreground/40 truncate">
                                                            {tool.description}
                                                        </p>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {isConnected && serverTools.length === 0 && (
                                    <div className="px-2 py-1 text-[10px] text-muted-foreground/40">
                                        无可用工具
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                );
            })}

            {/* Dialog */}
            <McpServerDialog
                open={dialogOpen}
                onOpenChange={setDialogOpen}
                onSave={handleSave}
                initialName={editingServer || ""}
                initialConfig={editConfig}
                mode={editingServer ? "edit" : "add"}
            />
        </div>
    );
}
