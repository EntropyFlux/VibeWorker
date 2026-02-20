"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
    Search,
    Plus,
    Trash2,
    ChevronRight,
    Calendar,
    FileText,
    X,
    Loader2,
    RefreshCw,
    BarChart3,
    User,
    Bot,
    Wrench,
    Zap,
    ChevronDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
    Tooltip,
    TooltipContent,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import {
    fetchMemoryEntries,
    addMemoryEntry,
    deleteMemoryEntry,
    fetchDailyLogs,
    deleteDailyLog,
    searchMemory,
    fetchMemoryStats,
    fetchRollingSummary,
    reindexMemory,
    type MemoryEntry,
    type MemoryStats,
    type MemorySearchResult,
    type DailyLog,
} from "@/lib/api";

type MemoryTab = "entries" | "logs" | "files";

const CATEGORY_OPTIONS = [
    { value: "", label: "全部" },
    { value: "preferences", label: "偏好" },
    { value: "facts", label: "事实" },
    { value: "tasks", label: "任务" },
    { value: "reflections", label: "反思" },
    { value: "procedural", label: "程序" },
    { value: "general", label: "通用" },
];

const CATEGORY_LABELS: Record<string, string> = {
    preferences: "偏好",
    facts: "事实",
    tasks: "任务",
    reflections: "反思",
    procedural: "程序",
    general: "通用",
};

// 来源标识图标和标签
const SOURCE_CONFIG: Record<string, { icon: typeof User; label: string; color: string }> = {
    user_explicit: { icon: User, label: "手动", color: "text-blue-500" },
    auto_extract: { icon: Bot, label: "提取", color: "text-green-500" },
    auto_reflection: { icon: Wrench, label: "反思", color: "text-orange-500" },
    user_correction: { icon: Zap, label: "纠正", color: "text-red-500" },
    api: { icon: Zap, label: "API", color: "text-purple-500" },
    migration: { icon: RefreshCw, label: "迁移", color: "text-muted-foreground" },
};

const WORKSPACE_FILES = [
    { name: "memory.json", path: "memory/memory.json", icon: "📝" },
    { name: "SOUL.md", path: "workspace/SOUL.md", icon: "💫" },
    { name: "IDENTITY.md", path: "workspace/IDENTITY.md", icon: "🪪" },
    { name: "USER.md", path: "workspace/USER.md", icon: "👤" },
    { name: "AGENTS.md", path: "workspace/AGENTS.md", icon: "📋" },
];

interface MemoryPanelProps {
    onFileOpen?: (path: string) => void;
}

function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes}B`;
    return `${(bytes / 1024).toFixed(1)}KB`;
}

// 重要性的颜色映射
function salienceColor(salience: number): string {
    if (salience >= 0.9) return "bg-red-500";
    if (salience >= 0.8) return "bg-amber-500";
    if (salience >= 0.5) return "bg-blue-500";
    return "bg-muted-foreground/30";
}

function SourceBadge({ source }: { source?: string }) {
    const config = SOURCE_CONFIG[source || ""] || SOURCE_CONFIG.api;
    const Icon = config.icon;
    return (
        <Tooltip>
            <TooltipTrigger asChild>
                <span className={`shrink-0 ${config.color}`}>
                    <Icon className="w-2.5 h-2.5" />
                </span>
            </TooltipTrigger>
            <TooltipContent side="top" className="text-[10px]">
                来源: {config.label}
            </TooltipContent>
        </Tooltip>
    );
}

export default function MemoryPanel({ onFileOpen }: MemoryPanelProps) {
    const [activeTab, setActiveTab] = useState<MemoryTab>("entries");
    const [entries, setEntries] = useState<MemoryEntry[]>([]);
    const [dailyLogs, setDailyLogs] = useState<DailyLog[]>([]);
    const [categoryFilter, setCategoryFilter] = useState("");
    const [searchQuery, setSearchQuery] = useState("");
    const [searchResults, setSearchResults] = useState<MemorySearchResult[] | null>(null);
    const [isSearching, setIsSearching] = useState(false);
    const [isLoading, setIsLoading] = useState(false);

    // 统计和摘要
    const [stats, setStats] = useState<MemoryStats | null>(null);
    const [rollingSummary, setRollingSummary] = useState("");
    const [showSummary, setShowSummary] = useState(false);

    // 添加表单
    const [showAddForm, setShowAddForm] = useState(false);
    const [newContent, setNewContent] = useState("");
    const [newCategory, setNewCategory] = useState("general");
    const [newSalience, setNewSalience] = useState(0.5);
    const [isAdding, setIsAdding] = useState(false);

    // 操作状态
    const [isReindexing, setIsReindexing] = useState(false);

    const loadEntries = useCallback(async () => {
        setIsLoading(true);
        try {
            const data = await fetchMemoryEntries(categoryFilter || undefined);
            setEntries(data.entries);
        } catch {
            // 后端可能未运行
        } finally {
            setIsLoading(false);
        }
    }, [categoryFilter]);

    const loadStats = useCallback(async () => {
        try {
            const [s, summary] = await Promise.all([
                fetchMemoryStats(),
                fetchRollingSummary(),
            ]);
            setStats(s);
            setRollingSummary(summary);
        } catch {
            // 后端可能未运行
        }
    }, []);

    const loadDailyLogs = useCallback(async () => {
        try {
            const logs = await fetchDailyLogs();
            setDailyLogs(logs);
        } catch {
            // 后端可能未运行
        }
    }, []);

    useEffect(() => {
        if (activeTab === "entries") {
            loadEntries();
            loadStats();
        }
        if (activeTab === "logs") loadDailyLogs();
    }, [activeTab, loadEntries, loadStats, loadDailyLogs]);

    const handleSearch = async () => {
        if (!searchQuery.trim()) return;
        setIsSearching(true);
        setSearchResults(null);
        try {
            const { results } = await searchMemory(searchQuery);
            setSearchResults(results);
        } catch {
            setSearchResults([]);
        } finally {
            setIsSearching(false);
        }
    };

    const handleAddEntry = async () => {
        if (!newContent.trim()) return;
        setIsAdding(true);
        try {
            await addMemoryEntry(newContent.trim(), newCategory, newSalience);
            setNewContent("");
            setNewSalience(0.5);
            setShowAddForm(false);
            await loadEntries();
            await loadStats();
        } catch {
            // Ignore
        } finally {
            setIsAdding(false);
        }
    };

    const handleDeleteEntry = async (e: React.MouseEvent, entryId: string) => {
        e.stopPropagation();
        try {
            await deleteMemoryEntry(entryId);
            await loadEntries();
            await loadStats();
        } catch {
            // Ignore
        }
    };

    const handleDeleteDailyLog = async (e: React.MouseEvent, date: string) => {
        e.stopPropagation();
        try {
            await deleteDailyLog(date);
            await loadDailyLogs();
        } catch {
            // Ignore
        }
    };

    const handleReindex = async () => {
        setIsReindexing(true);
        try {
            await reindexMemory();
        } catch {
            // Ignore
        } finally {
            setIsReindexing(false);
        }
    };

    return (
        <div className="flex flex-col h-full">
            {/* Tab Bar */}
            <div className="flex items-center gap-1 px-2 pt-1 pb-1">
                {(
                    [
                        { id: "entries", label: "记忆", icon: FileText },
                        { id: "logs", label: "日记", icon: Calendar },
                        { id: "files", label: "人格", icon: FileText },
                    ] as const
                ).map((tab) => (
                    <button
                        key={tab.id}
                        onClick={() => {
                            setActiveTab(tab.id);
                            setSearchResults(null);
                        }}
                        className={`flex-1 px-2 py-1.5 text-xs rounded-lg transition-all ${
                            activeTab === tab.id
                                ? "bg-primary/10 text-primary font-medium"
                                : "text-muted-foreground hover:bg-accent"
                        }`}
                    >
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Search Bar (entries & logs tabs) */}
            {activeTab !== "files" && (
                <div className="px-2 py-1.5">
                    <div className="relative">
                        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/50" />
                        <input
                            type="text"
                            placeholder="搜索记忆..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter") handleSearch();
                            }}
                            className="w-full h-7 pl-8 pr-8 text-xs rounded-lg border border-border/50 bg-background focus:outline-none focus:ring-1 focus:ring-primary/30 transition-all"
                        />
                        {searchQuery && (
                            <button
                                onClick={() => {
                                    setSearchQuery("");
                                    setSearchResults(null);
                                }}
                                className="absolute right-2 top-1/2 -translate-y-1/2"
                            >
                                <X className="w-3 h-3 text-muted-foreground/50 hover:text-muted-foreground" />
                            </button>
                        )}
                    </div>
                    {isSearching && (
                        <div className="flex items-center gap-1.5 mt-1.5 px-1">
                            <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />
                            <span className="text-[10px] text-muted-foreground">搜索中...</span>
                        </div>
                    )}
                </div>
            )}

            {/* Search Results */}
            {searchResults !== null && (
                <div className="px-2 pb-2">
                    <div className="p-2 rounded-lg bg-primary/5 border border-primary/10">
                        <div className="flex items-center justify-between mb-1.5">
                            <span className="text-[10px] font-medium text-primary">
                                {searchResults.length > 0
                                    ? `${searchResults.length} 条结果`
                                    : "无结果"}
                            </span>
                            <button onClick={() => setSearchResults(null)}>
                                <X className="w-3 h-3 text-muted-foreground/50 hover:text-muted-foreground" />
                            </button>
                        </div>
                        <div className="space-y-1.5 max-h-48 overflow-y-auto">
                            {searchResults.length === 0 && (
                                <p className="text-[10px] text-muted-foreground">
                                    未找到与 &quot;{searchQuery}&quot; 相关的记忆
                                </p>
                            )}
                            {searchResults.map((r, i) => (
                                <div key={i} className="p-1.5 rounded-md bg-background/50">
                                    <div className="flex items-center gap-1.5 mb-0.5">
                                        {r.category && (
                                            <span className="text-[9px] px-1 py-px rounded bg-primary/10 text-primary/70">
                                                {CATEGORY_LABELS[r.category] || r.category}
                                            </span>
                                        )}
                                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${salienceColor(r.salience ?? 0.5)}`} />
                                        <span className="text-[9px] text-muted-foreground/50 ml-auto">
                                            {(r.score * 100).toFixed(0)}%
                                        </span>
                                    </div>
                                    <p className="text-[10px] text-foreground/80 leading-relaxed break-words">
                                        {r.content}
                                    </p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            {/* Content */}
            <ScrollArea className="flex-1 overflow-hidden">
                <div className="p-2 space-y-1 w-full overflow-hidden">
                    {/* Entries Tab */}
                    {activeTab === "entries" && (
                        <>
                            {/* Rolling Summary */}
                            {rollingSummary && (
                                <button
                                    onClick={() => setShowSummary(!showSummary)}
                                    className="w-full mx-1 mb-1 p-2 rounded-lg bg-accent/30 border border-border/30 text-left transition-all hover:bg-accent/50"
                                >
                                    <div className="flex items-center gap-1.5">
                                        <BarChart3 className="w-3 h-3 text-primary/60 shrink-0" />
                                        <span className="text-[10px] font-medium text-primary/70">概要</span>
                                        <ChevronDown className={`w-3 h-3 text-muted-foreground/50 ml-auto transition-transform ${showSummary ? "rotate-180" : ""}`} />
                                    </div>
                                    {showSummary && (
                                        <p className="text-[10px] text-foreground/70 mt-1.5 leading-relaxed break-words">
                                            {rollingSummary}
                                        </p>
                                    )}
                                </button>
                            )}

                            {/* Category Filter + Actions */}
                            <div className="flex flex-wrap gap-1 px-1 pb-1.5">
                                {CATEGORY_OPTIONS.map((opt) => (
                                    <button
                                        key={opt.value}
                                        onClick={() => setCategoryFilter(opt.value)}
                                        className={`px-2 py-0.5 text-[10px] rounded-full transition-all ${
                                            categoryFilter === opt.value
                                                ? "bg-primary/15 text-primary font-medium"
                                                : "bg-accent/50 text-muted-foreground hover:bg-accent"
                                        }`}
                                    >
                                        {opt.label}
                                        {/* 分类计数 */}
                                        {stats && opt.value && stats.category_counts[opt.value] > 0 && (
                                            <span className="ml-0.5 text-muted-foreground/50">
                                                {stats.category_counts[opt.value]}
                                            </span>
                                        )}
                                    </button>
                                ))}
                                <div className="flex items-center gap-0.5 ml-auto">
                                    <Tooltip>
                                        <TooltipTrigger asChild>
                                            <button
                                                onClick={handleReindex}
                                                disabled={isReindexing}
                                                className="px-1 py-0.5 text-[10px] rounded-full bg-accent/50 text-muted-foreground hover:bg-accent transition-all disabled:opacity-50"
                                            >
                                                <RefreshCw className={`w-3 h-3 ${isReindexing ? "animate-spin" : ""}`} />
                                            </button>
                                        </TooltipTrigger>
                                        <TooltipContent>重建索引</TooltipContent>
                                    </Tooltip>
                                    <Tooltip>
                                        <TooltipTrigger asChild>
                                            <button
                                                onClick={() => setShowAddForm(!showAddForm)}
                                                className="px-1.5 py-0.5 text-[10px] rounded-full bg-primary/10 text-primary hover:bg-primary/20 transition-all"
                                            >
                                                <Plus className="w-3 h-3" />
                                            </button>
                                        </TooltipTrigger>
                                        <TooltipContent>添加记忆</TooltipContent>
                                    </Tooltip>
                                </div>
                            </div>

                            {/* Add Entry Form */}
                            {showAddForm && (
                                <div className="mx-1 p-2 rounded-lg border border-border/50 bg-card space-y-2">
                                    <textarea
                                        value={newContent}
                                        onChange={(e) => setNewContent(e.target.value)}
                                        placeholder="输入记忆内容..."
                                        className="w-full h-16 p-2 text-xs rounded-md border border-border/50 bg-background resize-none focus:outline-none focus:ring-1 focus:ring-primary/30"
                                    />
                                    <div className="flex items-center gap-2">
                                        <select
                                            value={newCategory}
                                            onChange={(e) => setNewCategory(e.target.value)}
                                            className="h-6 px-2 text-[10px] rounded border border-border/50 bg-background"
                                        >
                                            {CATEGORY_OPTIONS.filter((o) => o.value).map((opt) => (
                                                <option key={opt.value} value={opt.value}>
                                                    {opt.label}
                                                </option>
                                            ))}
                                        </select>
                                        <div className="flex items-center gap-1 flex-1">
                                            <input
                                                type="range"
                                                min={0}
                                                max={1}
                                                step={0.1}
                                                value={newSalience}
                                                onChange={(e) => setNewSalience(parseFloat(e.target.value))}
                                                className="flex-1 h-1 accent-primary"
                                            />
                                            <span className={`w-2 h-2 rounded-full shrink-0 ${salienceColor(newSalience)}`} />
                                            <span className="text-[10px] text-muted-foreground/70 w-5 text-right">
                                                {newSalience.toFixed(1)}
                                            </span>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <div className="flex-1" />
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="h-6 px-2 text-[10px]"
                                            onClick={() => setShowAddForm(false)}
                                        >
                                            取消
                                        </Button>
                                        <Button
                                            size="sm"
                                            className="h-6 px-3 text-[10px]"
                                            onClick={handleAddEntry}
                                            disabled={isAdding || !newContent.trim()}
                                        >
                                            {isAdding ? (
                                                <Loader2 className="w-3 h-3 animate-spin" />
                                            ) : (
                                                "添加"
                                            )}
                                        </Button>
                                    </div>
                                </div>
                            )}

                            {/* Entries List */}
                            {isLoading && entries.length === 0 && (
                                <div className="flex items-center justify-center py-6">
                                    <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                                </div>
                            )}
                            {!isLoading && entries.length === 0 && (
                                <div className="px-3 py-8 text-center">
                                    <p className="text-xs text-muted-foreground">暂无持久记忆</p>
                                    <p className="text-xs text-muted-foreground/60 mt-1">
                                        对话中会自动积累记忆
                                    </p>
                                </div>
                            )}
                            {entries.map((entry) => (
                                <div
                                    key={entry.entry_id}
                                    className="px-3 py-2 rounded-xl text-sm hover:bg-accent/50 transition-all group"
                                >
                                    <div className="flex items-center gap-1.5">
                                        {/* 来源图标 */}
                                        <SourceBadge source={entry.source} />
                                        {/* 重要性圆点 */}
                                        <Tooltip>
                                            <TooltipTrigger asChild>
                                                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${salienceColor(entry.salience ?? 0.5)}`} />
                                            </TooltipTrigger>
                                            <TooltipContent side="top" className="text-[10px]">
                                                重要性: {(entry.salience ?? 0.5).toFixed(1)}
                                            </TooltipContent>
                                        </Tooltip>
                                        {/* 分类标签 */}
                                        <span className="text-[10px] px-1.5 py-px rounded-full bg-primary/10 text-primary/70 shrink-0">
                                            {CATEGORY_LABELS[entry.category] || entry.category}
                                        </span>
                                        {/* 时间戳 */}
                                        <span className="text-[10px] text-muted-foreground/40 ml-auto shrink-0">
                                            {entry.timestamp}
                                        </span>
                                        {/* 访问次数 */}
                                        {entry.access_count && entry.access_count > 1 && (
                                            <span className="text-[9px] text-muted-foreground/30 shrink-0">
                                                x{entry.access_count}
                                            </span>
                                        )}
                                        {/* 删除按钮 */}
                                        <Trash2
                                            className="w-3 h-3 opacity-0 group-hover:opacity-40 hover:!opacity-100 hover:text-destructive shrink-0 transition-opacity cursor-pointer"
                                            onClick={(e) => handleDeleteEntry(e, entry.entry_id)}
                                        />
                                    </div>
                                    <p className="text-xs text-foreground/80 mt-1 break-words leading-relaxed">
                                        {entry.content}
                                    </p>
                                </div>
                            ))}

                            {/* Stats Footer */}
                            {stats && stats.total_entries > 0 && (
                                <div className="px-2 pt-2 pb-1 border-t border-border/30 mt-2">
                                    <div className="flex items-center justify-between text-[9px] text-muted-foreground/40">
                                        <span>{stats.total_entries} 条记忆</span>
                                        <span>v{stats.version || 2}</span>
                                    </div>
                                </div>
                            )}
                        </>
                    )}

                    {/* Daily Logs Tab */}
                    {activeTab === "logs" && (
                        <>
                            {dailyLogs.length === 0 && (
                                <div className="px-3 py-8 text-center">
                                    <p className="text-xs text-muted-foreground">暂无日记</p>
                                    <p className="text-xs text-muted-foreground/60 mt-1">
                                        对话过程中会自动生成每日日记
                                    </p>
                                </div>
                            )}
                            {dailyLogs.map((log) => (
                                <button
                                    key={log.date}
                                    className="w-full text-left px-3 py-2.5 rounded-xl text-sm hover:bg-accent transition-all duration-150 flex items-center gap-2 group"
                                    onClick={() => onFileOpen?.(log.path)}
                                >
                                    <Calendar className="w-3.5 h-3.5 text-primary/60 shrink-0" />
                                    <span className="flex-1 font-mono text-xs">{log.date}</span>
                                    <span className="text-[10px] text-muted-foreground/50">
                                        {formatSize(log.size)}
                                    </span>
                                    <Trash2
                                        className="w-3.5 h-3.5 opacity-0 group-hover:opacity-40 hover:!opacity-100 hover:text-destructive shrink-0 transition-opacity"
                                        onClick={(e) => handleDeleteDailyLog(e, log.date)}
                                    />
                                </button>
                            ))}
                        </>
                    )}

                    {/* Files Tab */}
                    {activeTab === "files" && (
                        <div className="space-y-1">
                            {WORKSPACE_FILES.map((file) => (
                                <button
                                    key={file.path}
                                    className="w-full text-left px-3 py-2.5 rounded-xl text-sm hover:bg-accent transition-all duration-150 flex items-center gap-2 group"
                                    onClick={() => onFileOpen?.(file.path)}
                                >
                                    <span>{file.icon}</span>
                                    <span className="flex-1">{file.name}</span>
                                    <ChevronRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-40 transition-opacity" />
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            </ScrollArea>
        </div>
    );
}
