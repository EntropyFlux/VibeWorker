"use client";

import React, { useState } from "react";
import { Download, Star, Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { RemoteSkill } from "@/lib/api";

interface SkillCardProps {
  skill: RemoteSkill;
  onInstall: (name: string) => Promise<void>;
  onSelect: (skill: RemoteSkill) => void;
  isInstalling?: boolean;
}

const CATEGORY_LABELS: Record<string, string> = {
  utility: "工具",
  data: "数据",
  web: "网络",
  automation: "自动化",
  integration: "集成",
  other: "其他",
};

const CATEGORY_COLORS: Record<string, string> = {
  utility: "bg-blue-100 text-blue-700",
  data: "bg-green-100 text-green-700",
  web: "bg-purple-100 text-purple-700",
  automation: "bg-orange-100 text-orange-700",
  integration: "bg-pink-100 text-pink-700",
  other: "bg-gray-100 text-gray-700",
};

export default function SkillCard({
  skill,
  onInstall,
  onSelect,
  isInstalling = false,
}: SkillCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const handleInstall = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await onInstall(skill.name);
  };

  const toggleExpand = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsExpanded(!isExpanded);
  };

  return (
    <div
      className="group p-4 rounded-xl border border-border/50 hover:border-primary/30 hover:shadow-md transition-all duration-200 cursor-pointer bg-card"
      onClick={() => onSelect(skill)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h4 className="font-semibold text-foreground truncate">
              {skill.name}
            </h4>
            <Badge
              variant="secondary"
              className={`text-[10px] px-1.5 py-0 ${
                CATEGORY_COLORS[skill.category] || CATEGORY_COLORS.other
              }`}
            >
              {CATEGORY_LABELS[skill.category] || skill.category}
            </Badge>
          </div>
          <p
            className={`text-sm text-muted-foreground mb-2 cursor-text ${
              isExpanded ? "" : "line-clamp-2"
            }`}
            onClick={toggleExpand}
          >
            {skill.description}
          </p>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <Star className="w-3 h-3 text-yellow-500 fill-yellow-500" />
              {skill.rating.toFixed(1)}
            </span>
            <span className="flex items-center gap-1">
              <Download className="w-3 h-3" />
              {skill.downloads}
            </span>
            <span className="text-muted-foreground/60">v{skill.version}</span>
          </div>
        </div>
        <div className="shrink-0">
          {skill.is_installed ? (
            <Button
              variant="outline"
              size="sm"
              className="h-8 text-green-600 border-green-200 hover:bg-green-50"
              disabled
            >
              <Check className="w-3.5 h-3.5 mr-1" />
              已安装
            </Button>
          ) : (
            <Button
              variant="default"
              size="sm"
              className="h-8"
              onClick={handleInstall}
              disabled={isInstalling}
            >
              {isInstalling ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                  安装中
                </>
              ) : (
                <>
                  <Download className="w-3.5 h-3.5 mr-1" />
                  安装
                </>
              )}
            </Button>
          )}
        </div>
      </div>
      {skill.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-3">
          {skill.tags.slice(0, 4).map((tag, index) => (
            <span
              key={`${tag}-${index}`}
              className="px-1.5 py-0.5 text-[10px] rounded bg-muted text-muted-foreground"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
