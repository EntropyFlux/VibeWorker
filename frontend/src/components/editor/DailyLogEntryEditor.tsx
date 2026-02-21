"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Save, Loader2, Calendar } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    Tooltip,
    TooltipContent,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import { updateDailyLogEntry, type DailyLogEntry } from "@/lib/api";

interface DailyLogEntryEditorProps {
    date: string;
    entry: DailyLogEntry;
    onSaved?: () => void;
    onClose: () => void;
}

export default function DailyLogEntryEditor({
    date,
    entry,
    onSaved,
    onClose,
}: DailyLogEntryEditorProps) {
    const [content, setContent] = useState(entry.content);
    const [isSaving, setIsSaving] = useState(false);
    const [saveStatus, setSaveStatus] = useState<"idle" | "saved" | "error">("idle");

    const hasChanges = content !== entry.content;

    // 条目切换时重置
    useEffect(() => {
        setContent(entry.content);
        setSaveStatus("idle");
    }, [date, entry.index, entry.content]);

    const handleSave = useCallback(async () => {
        if (!hasChanges || isSaving) return;
        setIsSaving(true);
        setSaveStatus("idle");
        try {
            await updateDailyLogEntry(date, entry.index, content.trim());
            setSaveStatus("saved");
            onSaved?.();
            setTimeout(() => setSaveStatus("idle"), 2000);
        } catch {
            setSaveStatus("error");
        } finally {
            setIsSaving(false);
        }
    }, [date, entry.index, content, hasChanges, isSaving, onSaved]);

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

    // 类型标签
    const typeLabel: Record<string, string> = {
        event: "事件",
        auto_extract: "自动提取",
        reflection: "日记",
    };

    return (
        <div className="flex flex-col h-full">
            {/* 头部 */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-border/50">
                <div className="flex items-center gap-2 min-w-0">
                    <Calendar className="w-3.5 h-3.5 text-primary/60 shrink-0" />
                    <span className="text-xs font-medium text-foreground/70 truncate">
                        {date} · [{entry.time}] {typeLabel[entry.type] || entry.type}
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

                {/* 元信息 */}
                <div className="pt-3 border-t border-border/30 space-y-1">
                    <p className="text-[10px] text-muted-foreground/50">
                        时间: {entry.time}
                    </p>
                    <p className="text-[10px] text-muted-foreground/50">
                        类型: {typeLabel[entry.type] || entry.type}
                    </p>
                    {entry.category && (
                        <p className="text-[10px] text-muted-foreground/50">
                            分类: {entry.category}
                        </p>
                    )}
                </div>
            </div>
        </div>
    );
}
