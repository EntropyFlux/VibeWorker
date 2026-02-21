"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  PanelRightClose,
  PanelRightOpen,
  Wifi,
  WifiOff,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import Sidebar from "@/components/sidebar/Sidebar";
import ChatPanel from "@/components/chat/ChatPanel";
import InspectorPanel, { type InspectorMode } from "@/components/editor/InspectorPanel";
import SettingsDialog, { initTheme } from "@/components/settings/SettingsDialog";
import { checkHealth, generateSessionTitle, type MemoryEntry, type DailyLogEntry } from "@/lib/api";
import { sessionStore } from "@/lib/sessionStore";

type ViewMode = "chat" | "memory" | "skills" | "mcp" | "cache";

// 面板宽度约束
const LEFT_MIN = 200;
const LEFT_MAX = 480;
const LEFT_DEFAULT = 300;
const RIGHT_MIN = 280;
const RIGHT_MAX = 600;
const RIGHT_DEFAULT = 384;

// localStorage 键名
const STORAGE_KEY_LEFT_WIDTH = "vibeworker_left_width";
const STORAGE_KEY_RIGHT_WIDTH = "vibeworker_right_width";

export default function HomePage() {
  const [currentView, setCurrentView] = useState<ViewMode>("chat");
  const [currentSessionId, setCurrentSessionId] = useState("main_session");
  const [inspectorFile, setInspectorFile] = useState<string | null>(null);
  const [showInspector, setShowInspector] = useState(false);
  const [isBackendOnline, setIsBackendOnline] = useState(false);
  const [debugMode, setDebugMode] = useState(false);

  // 记忆编辑状态
  const [inspectorMode, setInspectorMode] = useState<InspectorMode>("file");
  const [inspectorMemoryEntry, setInspectorMemoryEntry] = useState<MemoryEntry | null>(null);
  const [inspectorDailyLogEntry, setInspectorDailyLogEntry] = useState<{ date: string; entry: DailyLogEntry } | null>(null);
  const [memoryRefreshKey, setMemoryRefreshKey] = useState(0);

  // Resizable panel widths
  const [leftWidth, setLeftWidth] = useState(LEFT_DEFAULT);
  const [rightWidth, setRightWidth] = useState(RIGHT_DEFAULT);
  const draggingRef = useRef<"left" | "right" | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const sidebarRefreshRef = useRef<() => void>(() => {});

  // Initialize theme + panel widths from localStorage on mount
  useEffect(() => {
    initTheme();
    const savedDebug = localStorage.getItem("vibeworker_debug");
    if (savedDebug === "true") {
      setDebugMode(true);
      setShowInspector(true);
    }
    // 恢复面板宽度
    const savedLeft = localStorage.getItem(STORAGE_KEY_LEFT_WIDTH);
    if (savedLeft) {
      const v = Number(savedLeft);
      if (v >= LEFT_MIN && v <= LEFT_MAX) setLeftWidth(v);
    }
    const savedRight = localStorage.getItem(STORAGE_KEY_RIGHT_WIDTH);
    if (savedRight) {
      const v = Number(savedRight);
      if (v >= RIGHT_MIN && v <= RIGHT_MAX) setRightWidth(v);
    }
  }, []);

  // Listen for debug toggle from settings dialog
  useEffect(() => {
    const handler = (e: Event) => {
      const enabled = (e as CustomEvent).detail;
      setDebugMode(enabled);
      // Auto-open inspector when debug is enabled
      if (enabled) setShowInspector(true);
    };
    window.addEventListener("vibeworker-debug-toggle", handler);
    return () => window.removeEventListener("vibeworker-debug-toggle", handler);
  }, []);

  // Listen for debug activity (tool_start, debug_llm_call) to auto-open inspector
  useEffect(() => {
    const handler = (e: Event) => {
      const { sessionId: eventSessionId } = (e as CustomEvent).detail;
      // Only react to current session
      if (eventSessionId !== currentSessionId) return;
      // Auto-enable debug mode and open inspector
      setDebugMode(true);
      setShowInspector(true);
      // Persist debug mode preference
      localStorage.setItem("vibeworker_debug", "true");
    };
    window.addEventListener("vibeworker-debug-activity", handler);
    return () => window.removeEventListener("vibeworker-debug-activity", handler);
  }, [currentSessionId]);

  // Health check
  useEffect(() => {
    const check = async () => {
      const online = await checkHealth();
      setIsBackendOnline(online);
    };
    check();
    const interval = setInterval(check, 10000);
    return () => clearInterval(interval);
  }, []);

  // Register first-message callback for title generation
  useEffect(() => {
    sessionStore.setOnFirstMessage(async (sessionId: string) => {
      try {
        await generateSessionTitle(sessionId);
        sidebarRefreshRef.current();
      } catch (err) {
        console.error("Failed to generate session title:", err);
      }
    });
    return () => sessionStore.setOnFirstMessage(null);
  }, []);

  const handleFileOpen = useCallback((path: string) => {
    setInspectorFile(path);
    setInspectorMode("file");
    setInspectorMemoryEntry(null);
    setInspectorDailyLogEntry(null);
    setShowInspector(true);
  }, []);

  const handleInspectorClose = useCallback(() => {
    setShowInspector(false);
    setInspectorFile(null);
    setInspectorMode("file");
    setInspectorMemoryEntry(null);
    setInspectorDailyLogEntry(null);
  }, []);

  const handleMemoryEntryOpen = useCallback((entry: MemoryEntry) => {
    setInspectorMode("memory-entry");
    setInspectorMemoryEntry(entry);
    setInspectorDailyLogEntry(null);
    setInspectorFile(null);
    setShowInspector(true);
  }, []);

  const handleDailyLogEntryOpen = useCallback((date: string, entry: DailyLogEntry) => {
    setInspectorMode("daily-log-entry");
    setInspectorDailyLogEntry({ date, entry });
    setInspectorMemoryEntry(null);
    setInspectorFile(null);
    setShowInspector(true);
  }, []);

  const handleMemorySaved = useCallback(() => {
    setMemoryRefreshKey((k) => k + 1);
  }, []);

  const handleSessionSelect = useCallback((sessionId: string) => {
    setCurrentSessionId(sessionId);
    setCurrentView("chat");
  }, []);

  // ---- Drag resize logic ----
  const handleMouseDown = useCallback((side: "left" | "right") => {
    draggingRef.current = side;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  // 用 ref 追踪最新宽度，mouseUp 闭包中可以访问
  const leftWidthRef = useRef(leftWidth);
  const rightWidthRef = useRef(rightWidth);
  useEffect(() => { leftWidthRef.current = leftWidth; }, [leftWidth]);
  useEffect(() => { rightWidthRef.current = rightWidth; }, [rightWidth]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!draggingRef.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();

      if (draggingRef.current === "left") {
        const newWidth = Math.min(LEFT_MAX, Math.max(LEFT_MIN, e.clientX - rect.left));
        setLeftWidth(newWidth);
      } else if (draggingRef.current === "right") {
        const newWidth = Math.min(RIGHT_MAX, Math.max(RIGHT_MIN, rect.right - e.clientX));
        setRightWidth(newWidth);
      }
    };

    const handleMouseUp = () => {
      if (draggingRef.current) {
        // 拖拽结束时持久化宽度到 localStorage
        if (draggingRef.current === "left") {
          localStorage.setItem(STORAGE_KEY_LEFT_WIDTH, String(leftWidthRef.current));
        } else if (draggingRef.current === "right") {
          localStorage.setItem(STORAGE_KEY_RIGHT_WIDTH, String(rightWidthRef.current));
        }
        draggingRef.current = null;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      }
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  // Debug panel shows inside InspectorPanel when no file is open
  const activeDebug = debugMode && currentView === "chat";

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-background">
      {/* ============================================
          Top Navigation Bar
          ============================================ */}
      <header className="h-12 flex items-center justify-between px-4 border-b border-border/40 glass-subtle shrink-0 z-50">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <img src="/logo.png" alt="VibeWorker Logo" className="w-6 h-6" />
            <h1 className="text-sm font-semibold tracking-tight">
              VibeWorker
            </h1>
          </div>
          <span className="text-[10px] text-muted-foreground/50 font-mono bg-muted/50 px-1.5 py-0.5 rounded-md">
            v0.1.0
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Backend Status Indicator */}
          <Tooltip>
            <TooltipTrigger asChild>
              <div
                className={`flex items-center gap-1.5 px-2 py-1 rounded-lg text-[10px] font-medium transition-colors ${isBackendOnline
                  ? "text-green-600 bg-green-50"
                  : "text-muted-foreground bg-muted/50"
                  }`}
              >
                {isBackendOnline ? (
                  <Wifi className="w-3 h-3" />
                ) : (
                  <WifiOff className="w-3 h-3" />
                )}
                {isBackendOnline ? "在线" : "离线"}
              </div>
            </TooltipTrigger>
            <TooltipContent>
              {isBackendOnline
                ? "后端服务运行中 (localhost:8088)"
                : "后端服务未连接"}
            </TooltipContent>
          </Tooltip>

          {/* Settings Dialog */}
          <SettingsDialog />

          {/* Inspector Toggle */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="w-8 h-8 rounded-lg"
                onClick={() => setShowInspector(!showInspector)}
                id="toggle-inspector"
              >
                {showInspector ? (
                  <PanelRightClose className="w-4 h-4" />
                ) : (
                  <PanelRightOpen className="w-4 h-4" />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {showInspector ? "关闭面板" : "打开面板"}
            </TooltipContent>
          </Tooltip>
        </div>
      </header>

      {/* ============================================
          Main Content (Resizable Three-Column Layout)
          ============================================ */}
      <div ref={containerRef} className="flex-1 flex overflow-hidden">
        {/* Left Sidebar */}
        <aside
          className="border-r border-border/40 shrink-0 overflow-hidden bg-sidebar/50"
          style={{ width: leftWidth }}
        >
          <Sidebar
            currentSessionId={currentSessionId}
            onSessionSelect={handleSessionSelect}
            onViewChange={setCurrentView}
            currentView={currentView}
            onFileOpen={handleFileOpen}
            onRefreshReady={(refreshFn) => {
              sidebarRefreshRef.current = refreshFn;
            }}
            onMemoryEntryOpen={handleMemoryEntryOpen}
            onDailyLogEntryOpen={handleDailyLogEntryOpen}
            memoryRefreshKey={memoryRefreshKey}
          />
        </aside>

        {/* Left Resize Handle */}
        <div
          className="resize-handle"
          onMouseDown={() => handleMouseDown("left")}
        />

        {/* Center Stage */}
        <main className="flex-1 min-w-0">
          <ChatPanel
            sessionId={currentSessionId}
            onFileOpen={handleFileOpen}
          />
        </main>

        {/* Right Panel: Inspector + integrated Debug */}
        {showInspector && (
          <>
            <div
              className="resize-handle"
              onMouseDown={() => handleMouseDown("right")}
            />
            <aside
              className="border-l border-border/40 shrink-0 bg-card/50 overflow-hidden"
              style={{ width: rightWidth }}
            >
              <InspectorPanel
                filePath={inspectorFile}
                onClose={handleInspectorClose}
                onClearFile={() => setInspectorFile(null)}
                debugMode={activeDebug}
                sessionId={currentSessionId}
                mode={inspectorMode}
                memoryEntry={inspectorMemoryEntry}
                dailyLogEntry={inspectorDailyLogEntry}
                onMemorySaved={handleMemorySaved}
              />
            </aside>
          </>
        )}
      </div>
    </div>
  );
}
