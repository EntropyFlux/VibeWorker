"use client";

import React, { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from "@/components/ui/dialog";
import { addMemoryEntry } from "@/lib/api";

// 添加表单的分类选项
const ADD_CATEGORY_OPTIONS = [
    { value: "preferences", label: "偏好" },
    { value: "facts", label: "事实" },
    { value: "tasks", label: "任务" },
    { value: "reflections", label: "经验" },
    { value: "general", label: "通用" },
];

// 重要性的颜色映射
function salienceColor(salience: number): string {
    if (salience >= 0.9) return "bg-red-500";
    if (salience >= 0.8) return "bg-amber-500";
    if (salience >= 0.5) return "bg-blue-500";
    return "bg-muted-foreground/30";
}

interface AddMemoryDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onAdded?: () => void;
}

export default function AddMemoryDialog({
    open,
    onOpenChange,
    onAdded,
}: AddMemoryDialogProps) {
    const [content, setContent] = useState("");
    const [category, setCategory] = useState("general");
    const [salience, setSalience] = useState(0.5);
    const [isAdding, setIsAdding] = useState(false);

    const handleAdd = async () => {
        if (!content.trim()) return;
        setIsAdding(true);
        try {
            await addMemoryEntry(content.trim(), category, salience);
            setContent("");
            setSalience(0.5);
            setCategory("general");
            onOpenChange(false);
            onAdded?.();
        } catch {
            // 忽略
        } finally {
            setIsAdding(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-md">
                <DialogHeader>
                    <DialogTitle className="text-base">添加记忆</DialogTitle>
                </DialogHeader>

                <div className="space-y-3">
                    <textarea
                        value={content}
                        onChange={(e) => setContent(e.target.value)}
                        placeholder="输入记忆内容..."
                        className="w-full h-24 p-3 text-sm rounded-lg border border-border/50 bg-background resize-none focus:outline-none focus:ring-1 focus:ring-primary/30"
                        autoFocus
                    />

                    <div className="flex items-center gap-3">
                        <label className="text-xs text-muted-foreground shrink-0">分类</label>
                        <select
                            value={category}
                            onChange={(e) => setCategory(e.target.value)}
                            className="h-7 px-2 text-xs rounded-md border border-border/50 bg-background"
                        >
                            {ADD_CATEGORY_OPTIONS.map((opt) => (
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
                </div>

                <DialogFooter>
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onOpenChange(false)}
                    >
                        取消
                    </Button>
                    <Button
                        size="sm"
                        onClick={handleAdd}
                        disabled={isAdding || !content.trim()}
                    >
                        {isAdding ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                            "添加"
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
