"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Save, Loader2, Brain } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    Tooltip,
    TooltipContent,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import { updateMemoryEntry, type MemoryEntry } from "@/lib/api";

// 分类选项
const CATEGORY_OPTIONS = [
    { value: "preferences", label: "偏好" },
    { value: "facts", label: "事实" },
    { value: "tasks", label: "任务" },
    { value: "reflections", label: "经验" },
    { value: "procedural", label: "程序经验" },
    { value: "general", label: "通用" },
];

// 重要性颜色
function salienceColor(salience: number): string {
    if (salience >= 0.9) return "bg-red-500";
    if (salience >= 0.8) return "bg-amber-500";
    if (salience >= 0.5) return "bg-blue-500";
    return "bg-muted-foreground/30";
}

interface MemoryEntryEditorProps {
    entry: MemoryEntry;
    onSaved?: () => void;
    onClose: () => void;
}

export default function MemoryEntryEditor({
    entry,
    onSaved,
    onClose,
}: MemoryEntryEditorProps) {
    const [content, setContent] = useState(entry.content);
    const [category, setCategory] = useState(entry.category);
    const [salience, setSalience] = useState(entry.salience ?? 0.5);
    const [isSaving, setIsSaving] = useState(false);
    const [saveStatus, setSaveStatus] = useState<"idle" | "saved" | "error">("idle");

    const hasChanges =
        content !== entry.content ||
        category !== entry.category ||
        salience !== (entry.salience ?? 0.5);

    // 条目切换时重置
    useEffect(() => {
        setContent(entry.content);
        setCategory(entry.category);
        setSalience(entry.salience ?? 0.5);
        setSaveStatus("idle");
    }, [entry.entry_id, entry.content, entry.category, entry.salience]);

    const handleSave = useCallback(async () => {
        if (!hasChanges || isSaving) return;
        setIsSaving(true);
        setSaveStatus("idle");
        try {
            await updateMemoryEntry(entry.entry_id, {
                content: content.trim(),
                category,
                salience,
            });
            setSaveStatus("saved");
            onSaved?.();
            setTimeout(() => setSaveStatus("idle"), 2000);
        } catch {
            setSaveStatus("error");
        } finally {
            setIsSaving(false);
        }
    }, [entry.entry_id, content, category, salience, hasChanges, isSaving, onSaved]);

    // Ctrl+S 快捷保存
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "s") {
                e.preventDefault();
                handleSave();
            }
        };
        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, [handleSave]);

    return (
        <div className="flex flex-col h-full">
            {/* 头部 */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-border/50">
                <div className="flex items-center gap-2 min-w-0">
                    <Brain className="w-3.5 h-3.5 text-primary/60 shrink-0" />
                    <span className="text-xs font-medium text-foreground/70 truncate">
                        长期记忆 · {entry.entry_id}
                    </span>
                    {hasChanges && (
                        <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0" />
                    )}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                    {hasChanges && (
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="w-6 h-6 rounded-md text-primary hover:bg-primary/10"
                                    onClick={handleSave}
                                    disabled={isSaving}
                                >
                                    {isSaving ? (
                                        <Loader2 className="w-3 h-3 animate-spin" />
                                    ) : (
                                        <Save className="w-3 h-3" />
                                    )}
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent>保存 (Ctrl+S)</TooltipContent>
                        </Tooltip>
                    )}
                    {saveStatus === "saved" && (
                        <span className="text-[10px] text-green-600 font-medium px-1">
                            已保存
                        </span>
                    )}
                    {saveStatus === "error" && (
                        <span className="text-[10px] text-destructive font-medium px-1">
                            保存失败
                        </span>
                    )}
                    <Button
                        variant="ghost"
                        size="icon"
                        className="w-6 h-6 rounded-md"
                        onClick={onClose}
                    >
                        <span className="text-xs">✕</span>
                    </Button>
                </div>
            </div>

            {/* 编辑区 */}
            <div className="flex-1 p-4 space-y-4 overflow-y-auto">
                <div>
                    <label className="text-xs text-muted-foreground mb-1.5 block">内容</label>
                    <textarea
                        value={content}
                        onChange={(e) => setContent(e.target.value)}
                        className="w-full min-h-[200px] p-3 text-sm rounded-lg border border-border/50 bg-background resize-y focus:outline-none focus:ring-1 focus:ring-primary/30 leading-relaxed"
                    />
                </div>

                <div className="flex items-center gap-3">
                    <label className="text-xs text-muted-foreground shrink-0">分类</label>
                    <select
                        value={category}
                        onChange={(e) => setCategory(e.target.value)}
                        className="h-7 px-2 text-xs rounded-md border border-border/50 bg-background"
                    >
                        {CATEGORY_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                                {opt.label}
                            </option>
                        ))}
                    </select>
                </div>

                <div className="flex items-center gap-3">
                    <label className="text-xs text-muted-foreground shrink-0">重要性</label>
                    <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.1}
                        value={salience}
                        onChange={(e) => setSalience(parseFloat(e.target.value))}
                        className="flex-1 h-1 accent-primary"
                    />
                    <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${salienceColor(salience)}`} />
                    <span className="text-xs text-muted-foreground w-6 text-right">
                        {salience.toFixed(1)}
                    </span>
                </div>

                {/* 元信息 */}
                <div className="pt-3 border-t border-border/30 space-y-1">
                    <p className="text-[10px] text-muted-foreground/50">
                        创建于: {entry.timestamp}
                    </p>
                    {entry.source && (
                        <p className="text-[10px] text-muted-foreground/50">
                            来源: {entry.source}
                        </p>
                    )}
                    {entry.access_count && entry.access_count > 1 && (
                        <p className="text-[10px] text-muted-foreground/50">
                            访问次数: {entry.access_count}
                        </p>
                    )}
                </div>
            </div>
        </div>
    );
}
