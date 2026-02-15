"use client";

import React, { useState, useEffect } from "react";
import { Settings, Eye, EyeOff, Loader2, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fetchSettings, updateSettings, type SettingsData } from "@/lib/api";

function SettingsField({
    label,
    value,
    onChange,
    placeholder,
    type = "text",
    secret = false,
}: {
    label: string;
    value: string;
    onChange: (v: string) => void;
    placeholder?: string;
    type?: string;
    secret?: boolean;
}) {
    const [visible, setVisible] = useState(false);

    return (
        <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">{label}</label>
            <div className="relative">
                <input
                    type={secret && !visible ? "password" : type}
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    placeholder={placeholder}
                    className="w-full h-8 px-3 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 transition-all font-mono"
                />
                {secret && (
                    <button
                        type="button"
                        onClick={() => setVisible(!visible)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground/50 hover:text-muted-foreground transition-colors"
                    >
                        {visible ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    </button>
                )}
            </div>
        </div>
    );
}

export default function SettingsDialog() {
    const [open, setOpen] = useState(false);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [form, setForm] = useState<SettingsData>({
        openai_api_key: "",
        openai_api_base: "",
        llm_model: "",
        llm_temperature: 0.7,
        llm_max_tokens: 4096,
        embedding_api_key: "",
        embedding_api_base: "",
        embedding_model: "",
        translate_api_key: "",
        translate_api_base: "",
        translate_model: "",
        memory_auto_extract: false,
        memory_daily_log_days: 2,
        memory_max_prompt_tokens: 4000,
        memory_index_enabled: true,
    });

    useEffect(() => {
        if (open) {
            setLoading(true);
            fetchSettings()
                .then((data) => setForm(data))
                .catch(() => { })
                .finally(() => setLoading(false));
        }
    }, [open]);

    const handleSave = async () => {
        setSaving(true);
        try {
            await updateSettings(form);
            setOpen(false);
        } catch {
            // ignore
        } finally {
            setSaving(false);
        }
    };

    const updateField = (key: keyof SettingsData, value: string | number | boolean) => {
        setForm((prev) => ({ ...prev, [key]: value }));
    };

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button
                    variant="ghost"
                    size="icon"
                    className="w-8 h-8 rounded-lg"
                    id="settings-button"
                >
                    <Settings className="w-4 h-4" />
                </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[480px]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Settings className="w-4 h-4" />
                        模型配置
                    </DialogTitle>
                    <DialogDescription>
                        配置主模型、Embedding 和翻译模型。保存后需重启后端生效。
                    </DialogDescription>
                </DialogHeader>

                {loading ? (
                    <div className="flex items-center justify-center py-8">
                        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                    </div>
                ) : (
                    <Tabs defaultValue="llm" className="w-full">
                        <TabsList className="grid w-full grid-cols-4 mb-4">
                            <TabsTrigger value="llm" className="text-xs">
                                <span className="w-1.5 h-1.5 rounded-full bg-blue-500 mr-1.5" />
                                主模型
                            </TabsTrigger>
                            <TabsTrigger value="embedding" className="text-xs">
                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5" />
                                Embedding
                            </TabsTrigger>
                            <TabsTrigger value="translate" className="text-xs">
                                <span className="w-1.5 h-1.5 rounded-full bg-orange-500 mr-1.5" />
                                翻译
                            </TabsTrigger>
                            <TabsTrigger value="memory" className="text-xs">
                                <span className="w-1.5 h-1.5 rounded-full bg-purple-500 mr-1.5" />
                                记忆
                            </TabsTrigger>
                        </TabsList>

                        {/* LLM Tab */}
                        <TabsContent value="llm" className="space-y-3 mt-0">
                            <SettingsField
                                label="API Key"
                                value={form.openai_api_key}
                                onChange={(v) => updateField("openai_api_key", v)}
                                placeholder="sk-..."
                                secret
                            />
                            <SettingsField
                                label="API Base URL"
                                value={form.openai_api_base}
                                onChange={(v) => updateField("openai_api_base", v)}
                                placeholder="https://api.openai.com/v1"
                            />
                            <SettingsField
                                label="模型名称"
                                value={form.llm_model}
                                onChange={(v) => updateField("llm_model", v)}
                                placeholder="gpt-4o"
                            />
                            <div className="grid grid-cols-2 gap-3">
                                <SettingsField
                                    label="Temperature"
                                    value={String(form.llm_temperature)}
                                    onChange={(v) => updateField("llm_temperature", parseFloat(v) || 0)}
                                    type="number"
                                />
                                <SettingsField
                                    label="Max Tokens"
                                    value={String(form.llm_max_tokens)}
                                    onChange={(v) => updateField("llm_max_tokens", parseInt(v) || 4096)}
                                    type="number"
                                />
                            </div>
                        </TabsContent>

                        {/* Embedding Tab */}
                        <TabsContent value="embedding" className="space-y-3 mt-0">
                            <p className="text-xs text-muted-foreground mb-3">
                                留空则自动复用主模型的 API 配置
                            </p>
                            <SettingsField
                                label="API Key"
                                value={form.embedding_api_key}
                                onChange={(v) => updateField("embedding_api_key", v)}
                                placeholder="留空复用主模型"
                                secret
                            />
                            <SettingsField
                                label="API Base URL"
                                value={form.embedding_api_base}
                                onChange={(v) => updateField("embedding_api_base", v)}
                                placeholder="留空复用主模型"
                            />
                            <SettingsField
                                label="模型名称"
                                value={form.embedding_model}
                                onChange={(v) => updateField("embedding_model", v)}
                                placeholder="text-embedding-3-small"
                            />
                        </TabsContent>

                        {/* Translate Tab */}
                        <TabsContent value="translate" className="space-y-3 mt-0">
                            <p className="text-xs text-muted-foreground mb-3">
                                留空则自动复用主模型，可配置更轻量的模型用于翻译
                            </p>
                            <SettingsField
                                label="API Key"
                                value={form.translate_api_key}
                                onChange={(v) => updateField("translate_api_key", v)}
                                placeholder="留空复用主模型"
                                secret
                            />
                            <SettingsField
                                label="API Base URL"
                                value={form.translate_api_base}
                                onChange={(v) => updateField("translate_api_base", v)}
                                placeholder="留空复用主模型"
                            />
                            <SettingsField
                                label="模型名称"
                                value={form.translate_model}
                                onChange={(v) => updateField("translate_model", v)}
                                placeholder="gpt-4o-mini"
                            />
                        </TabsContent>

                        {/* Memory Tab */}
                        <TabsContent value="memory" className="space-y-3 mt-0">
                            <p className="text-xs text-muted-foreground mb-3">
                                配置记忆系统行为，包括自动提取和日志注入
                            </p>
                            <div className="space-y-1">
                                <label className="text-xs font-medium text-muted-foreground">自动提取记忆</label>
                                <div className="flex items-center gap-2">
                                    <button
                                        type="button"
                                        onClick={() => updateField("memory_auto_extract", !form.memory_auto_extract)}
                                        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${form.memory_auto_extract ? "bg-primary" : "bg-border"}`}
                                    >
                                        <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${form.memory_auto_extract ? "translate-x-4.5" : "translate-x-0.5"}`} />
                                    </button>
                                    <span className="text-xs text-muted-foreground">
                                        {form.memory_auto_extract ? "开启" : "关闭"}
                                        <span className="text-[10px] text-muted-foreground/50 ml-1">
                                            (会产生额外 LLM 调用)
                                        </span>
                                    </span>
                                </div>
                            </div>
                            <div className="space-y-1">
                                <label className="text-xs font-medium text-muted-foreground">语义搜索索引</label>
                                <div className="flex items-center gap-2">
                                    <button
                                        type="button"
                                        onClick={() => updateField("memory_index_enabled", !form.memory_index_enabled)}
                                        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${form.memory_index_enabled ? "bg-primary" : "bg-border"}`}
                                    >
                                        <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${form.memory_index_enabled ? "translate-x-4.5" : "translate-x-0.5"}`} />
                                    </button>
                                    <span className="text-xs text-muted-foreground">
                                        {form.memory_index_enabled ? "开启" : "关闭（降级为关键词搜索）"}
                                    </span>
                                </div>
                            </div>
                            <SettingsField
                                label="日志加载天数"
                                value={String(form.memory_daily_log_days)}
                                onChange={(v) => updateField("memory_daily_log_days", parseInt(v) || 2)}
                                type="number"
                                placeholder="2"
                            />
                            <SettingsField
                                label="记忆 Token 预算"
                                value={String(form.memory_max_prompt_tokens)}
                                onChange={(v) => updateField("memory_max_prompt_tokens", parseInt(v) || 4000)}
                                type="number"
                                placeholder="4000"
                            />
                        </TabsContent>
                    </Tabs>
                )}

                <DialogFooter>
                    <Button
                        onClick={handleSave}
                        disabled={saving || loading}
                        size="sm"
                        className="gap-1.5"
                    >
                        {saving ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                            <Save className="w-3.5 h-3.5" />
                        )}
                        保存配置
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
