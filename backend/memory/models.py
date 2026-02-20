"""记忆系统数据模型

定义记忆条目、元数据、日志条目等核心数据结构。
支持 JSON 序列化/反序列化，保持向后兼容。
"""
import hashlib
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Any


# ============================================
# 分类定义
# ============================================

# 6 大分类（新增 procedural）
VALID_CATEGORIES = [
    "preferences",  # 用户偏好、习惯
    "facts",        # 重要事实
    "tasks",        # 任务备忘
    "reflections",  # 反思总结（非工具相关）
    "procedural",   # 程序性记忆（工具使用经验、环境特性）
    "general",      # 通用信息
]

CATEGORY_LABELS = {
    "preferences": "用户偏好",
    "facts": "重要事实",
    "tasks": "任务备忘",
    "reflections": "反思日志",
    "procedural": "程序经验",
    "general": "通用记忆",
}


# ============================================
# 数据模型
# ============================================

@dataclass
class MemoryMeta:
    """记忆元数据"""
    version: int = 2
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    rolling_summary: str = ""


@dataclass
class MemoryEntry:
    """单条记忆条目（长期记忆）

    字段说明：
    - id: 唯一标识符（8 位十六进制）
    - category: 分类（preferences/facts/tasks/reflections/procedural/general）
    - content: 记忆内容
    - salience: 重要性评分（0.0-1.0，默认 0.5）
    - created_at: 创建时间（ISO 格式）
    - last_accessed: 最后访问时间
    - access_count: 访问次数（用于热度计算）
    - source: 来源（user_explicit/auto_extract/auto_reflection）
    - context: 额外上下文信息（JSON 对象）
    """
    id: str
    category: str
    content: str
    salience: float = 0.5
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_accessed: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 1
    source: str = "user_explicit"
    context: Optional[dict[str, Any]] = None

    @staticmethod
    def generate_id(content: str = "", timestamp: str = "") -> str:
        """生成唯一 ID（8 位十六进制）"""
        if content and timestamp:
            # 基于内容和时间戳生成确定性 ID（兼容旧逻辑）
            raw = f"{timestamp}:{content}"
            return hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]
        # 否则使用 UUID
        return uuid.uuid4().hex[:8]

    def to_dict(self) -> dict:
        """转换为字典（用于 JSON 序列化）"""
        d = asdict(self)
        # 确保 context 为 None 时不输出空 dict
        if d.get("context") is None:
            del d["context"]
        return d

    def to_api_dict(self) -> dict:
        """转换为 API 响应格式（兼容旧接口）

        返回格式：
        {
            "entry_id": "...",      # 兼容旧字段名
            "content": "...",
            "category": "...",
            "timestamp": "YYYY-MM-DD",  # 兼容旧字段名
            "salience": 0.5,        # 重要性评分
            "access_count": 1,      # 访问计数
            "source": "...",        # 来源标识
        }
        """
        # 从 ISO 格式提取日期部分
        date_part = self.created_at[:10] if len(self.created_at) >= 10 else self.created_at
        return {
            "entry_id": self.id,
            "content": self.content,
            "category": self.category,
            "timestamp": date_part,
            "salience": self.salience,
            "access_count": self.access_count,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        """从字典创建实例"""
        return cls(
            id=data.get("id", cls.generate_id()),
            category=data.get("category", "general"),
            content=data.get("content", ""),
            salience=data.get("salience", 0.5),
            created_at=data.get("created_at", datetime.now().isoformat()),
            last_accessed=data.get("last_accessed", datetime.now().isoformat()),
            access_count=data.get("access_count", 1),
            source=data.get("source", "user_explicit"),
            context=data.get("context"),
        )



@dataclass
class DailyLogEntry:
    """每日日志条目

    字段说明：
    - time: 时间（HH:MM:SS）
    - type: 类型（event/auto_extract/reflection）
    - content: 内容
    - category: 分类（可选，用于 auto_extract）
    - tool: 工具名（可选，用于 reflection）
    - error: 错误信息（可选，用于 reflection）
    """
    time: str
    type: str
    content: str
    category: Optional[str] = None
    tool: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """转换为字典"""
        d = {
            "time": self.time,
            "type": self.type,
            "content": self.content,
        }
        if self.category:
            d["category"] = self.category
        if self.tool:
            d["tool"] = self.tool
        if self.error:
            d["error"] = self.error
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DailyLogEntry":
        """从字典创建实例"""
        return cls(
            time=data.get("time", ""),
            type=data.get("type", "event"),
            content=data.get("content", ""),
            category=data.get("category"),
            tool=data.get("tool"),
            error=data.get("error"),
        )


@dataclass
class DailyLog:
    """每日日志文件"""
    date: str
    entries: list[DailyLogEntry] = field(default_factory=list)
    summary: Optional[str] = None
    archived: bool = False

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "date": self.date,
            "entries": [e.to_dict() for e in self.entries],
            "summary": self.summary,
            "archived": self.archived,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DailyLog":
        """从字典创建实例"""
        return cls(
            date=data.get("date", ""),
            entries=[DailyLogEntry.from_dict(e) for e in data.get("entries", [])],
            summary=data.get("summary"),
            archived=data.get("archived", False),
        )
