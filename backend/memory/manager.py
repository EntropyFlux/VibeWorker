"""记忆管理器 — VibeWorker 记忆系统 v2 的中枢

管理长期记忆（memory.json）和每日日志（logs/YYYY-MM-DD.json）。
支持结构化条目管理、重要性评分、时间衰减、每日日志操作和统计功能。

主要改进：
- memory.json 替代 MEMORY.md，结构化存储
- 支持 salience（重要性）、access_count（访问计数）
- 支持 procedural 分类（程序性记忆）
- 每日日志使用 JSON 格式
- 自动迁移旧格式数据
"""
import json
import logging
import re
import shutil
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from config import settings
from memory.models import (
    MemoryEntry,
    MemoryMeta,
    DailyLog,
    DailyLogEntry,
    VALID_CATEGORIES,
    CATEGORY_LABELS,
)

logger = logging.getLogger(__name__)


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    """计算两段文本的 Jaccard 相似度（基于分词的集合交并比）

    用于轻量级重复检测，无需 LLM 调用。
    """
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return intersection / union if union > 0 else 0.0


class MemoryManager:
    """记忆管理核心类"""

    # 重复检测的相似度阈值（Jaccard）
    DUPLICATE_SIMILARITY_THRESHOLD = 0.7

    # Prompt 注入时的条目数量限制（避免生成海量文本再截断）
    PROMPT_MAX_ENTRIES_PER_CATEGORY = 20
    PROMPT_MAX_TOTAL_ENTRIES = 50

    def __init__(self):
        self.memory_dir = settings.memory_dir
        self.logs_dir = settings.memory_dir / "logs"
        self.memory_file = settings.memory_dir / "memory.json"
        self.legacy_memory_file = settings.memory_dir / "MEMORY.md"
        self.backup_file = settings.memory_dir / "memory.json.bak"

        # 并发写保护锁（read-modify-write 操作需持有此锁）
        self._lock = threading.Lock()

        # 确保目录存在
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # 自动迁移旧格式
        self._migrate_if_needed()

    # ============================================
    # 自动迁移
    # ============================================

    def _migrate_if_needed(self) -> None:
        """检查并执行必要的迁移

        迁移场景：
        1. 存在 MEMORY.md 但不存在 memory.json → 迁移长期记忆
        2. 存在 .md 日志但不存在 .json 日志 → 迁移每日日志
        """
        # 迁移长期记忆
        if self.legacy_memory_file.exists() and not self.memory_file.exists():
            self._migrate_memory_md()

        # 迁移每日日志（.md → .json）
        self._migrate_daily_logs()

    def _migrate_memory_md(self) -> None:
        """从 MEMORY.md 迁移到 memory.json"""
        logger.info("开始迁移 MEMORY.md → memory.json")

        try:
            content = self.legacy_memory_file.read_text(encoding="utf-8")
            entries = self._parse_legacy_memory(content)

            # 创建新的 memory.json
            data = {
                "version": 2,
                "last_updated": datetime.now().isoformat(),
                "rolling_summary": "",
                "memories": [e.to_dict() for e in entries],
            }

            self._save_memory_json(data)
            logger.info(f"成功迁移 {len(entries)} 条记忆到 memory.json")

            # 备份旧文件
            backup_path = self.memory_dir / "MEMORY.md.migrated"
            shutil.copy2(self.legacy_memory_file, backup_path)
            logger.info(f"旧文件已备份到 {backup_path}")

        except Exception as e:
            logger.error(f"迁移 MEMORY.md 失败: {e}")

    def _parse_legacy_memory(self, content: str) -> list[MemoryEntry]:
        """解析旧版 MEMORY.md 格式

        每条记录为一行列表项：`- [YYYY-MM-DD] content` 或 `- [YYYY-MM-DD][id] content`
        """
        entries = []
        current_category = "general"

        # 分类标题映射
        category_headers = {
            "## 用户偏好": "preferences",
            "## 重要事实": "facts",
            "## 任务备忘": "tasks",
            "## 反思日志": "reflections",
            "## 通用记忆": "general",
        }

        for line in content.split("\n"):
            stripped = line.strip()

            # 检测分类标题
            for header, cat in category_headers.items():
                if stripped.startswith(header):
                    current_category = cat
                    break

            # 解析条目行
            match = re.match(
                r"^-\s+\[(\d{4}-\d{2}-\d{2})\](?:\[([a-f0-9]+)\])?\s*(.+)$",
                stripped,
            )
            if match:
                timestamp = match.group(1)
                entry_id = match.group(2) or ""
                entry_content = match.group(3)

                entry = MemoryEntry.from_legacy(
                    content=entry_content,
                    category=current_category,
                    timestamp=timestamp,
                    entry_id=entry_id,
                )
                entries.append(entry)

        return entries

    def _migrate_daily_logs(self) -> None:
        """迁移 .md 格式的每日日志到 .json 格式"""
        if not self.logs_dir.exists():
            return

        for md_file in self.logs_dir.glob("*.md"):
            # 检查日期格式
            if not re.match(r"\d{4}-\d{2}-\d{2}", md_file.stem):
                continue

            json_file = self.logs_dir / f"{md_file.stem}.json"
            if json_file.exists():
                continue  # 已迁移

            try:
                content = md_file.read_text(encoding="utf-8")
                entries = self._parse_legacy_daily_log(content)

                daily_log = DailyLog(
                    date=md_file.stem,
                    entries=entries,
                    summary=None,
                    archived=False,
                )

                json_file.write_text(
                    json.dumps(daily_log.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                logger.info(f"迁移每日日志: {md_file.name} → {json_file.name}")

                # 备份旧文件
                backup_path = md_file.with_suffix(".md.migrated")
                md_file.rename(backup_path)

            except Exception as e:
                logger.warning(f"迁移 {md_file.name} 失败: {e}")

    def _parse_legacy_daily_log(self, content: str) -> list[DailyLogEntry]:
        """解析旧版每日日志格式

        格式：`- [HH:MM] content` 或 `- [HH:MM] [auto] [category] content`
        """
        entries = []

        for line in content.split("\n"):
            stripped = line.strip()

            # 解析条目行
            match = re.match(r"^-\s+\[(\d{2}:\d{2})\]\s*(.+)$", stripped)
            if match:
                time = match.group(1) + ":00"  # 补全秒数
                rest = match.group(2)

                # 检查是否为自动提取
                auto_match = re.match(r"^\[auto\]\s*\[(\w+)\]\s*(.+)$", rest)
                if auto_match:
                    category = auto_match.group(1)
                    entry_content = auto_match.group(2)
                    entries.append(DailyLogEntry(
                        time=time,
                        type="auto_extract",
                        content=entry_content,
                        category=category,
                    ))
                else:
                    entries.append(DailyLogEntry(
                        time=time,
                        type="event",
                        content=rest,
                    ))

        return entries

    # ============================================
    # memory.json 操作
    # ============================================

    def _load_memory_json(self) -> dict:
        """加载 memory.json"""
        if not self.memory_file.exists():
            return {
                "version": 2,
                "last_updated": datetime.now().isoformat(),
                "rolling_summary": "",
                "memories": [],
            }

        try:
            return json.loads(self.memory_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.error(f"memory.json 解析失败: {e}")
            return {
                "version": 2,
                "last_updated": datetime.now().isoformat(),
                "rolling_summary": "",
                "memories": [],
            }

    def _save_memory_json(self, data: dict) -> None:
        """保存 memory.json（带自动备份）"""
        # 更新时间戳
        data["last_updated"] = datetime.now().isoformat()

        # 创建备份
        if self.memory_file.exists():
            try:
                shutil.copy2(self.memory_file, self.backup_file)
            except Exception as e:
                logger.warning(f"创建备份失败: {e}")

        # 写入文件
        self.memory_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def read_memory(self) -> str:
        """读取记忆内容（返回人类可读格式，用于 System Prompt）

        返回格式化的记忆摘要，包含：
        - Rolling Summary
        - 按分类组织的记忆条目
        - 重要性标记
        """
        data = self._load_memory_json()
        memories = [MemoryEntry.from_dict(m) for m in data.get("memories", [])]

        if not memories:
            return ""

        parts = []

        # Rolling Summary
        summary = data.get("rolling_summary", "")
        if summary:
            parts.append(f"## 概要\n{summary}")

        # 按分类组织
        by_category: dict[str, list[MemoryEntry]] = {}
        for m in memories:
            by_category.setdefault(m.category, []).append(m)

        # 按重要性排序，限制条目数量避免 Prompt 过长
        total_count = 0
        for cat in VALID_CATEGORIES:
            cat_entries = by_category.get(cat, [])
            if not cat_entries:
                continue

            # 按 salience 降序排序，优先保留高重要性条目
            cat_entries.sort(key=lambda x: x.salience, reverse=True)
            cat_entries = cat_entries[:self.PROMPT_MAX_ENTRIES_PER_CATEGORY]

            # 检查总量限制
            remaining = self.PROMPT_MAX_TOTAL_ENTRIES - total_count
            if remaining <= 0:
                break
            cat_entries = cat_entries[:remaining]
            total_count += len(cat_entries)

            label = CATEGORY_LABELS.get(cat, cat)
            lines = [f"## {label}"]
            for e in cat_entries:
                # 显示重要性标记
                importance = "⭐" if e.salience >= 0.8 else ""
                lines.append(f"- {importance}{e.content}")

            parts.append("\n".join(lines))

        return "\n\n".join(parts)

    def get_entries(self, category: Optional[str] = None) -> list[dict]:
        """获取记忆条目列表（API 格式）

        Args:
            category: 可选的分类过滤

        Returns:
            条目列表，每条包含 entry_id, content, category, timestamp, salience, access_count
        """
        data = self._load_memory_json()
        memories = [MemoryEntry.from_dict(m) for m in data.get("memories", [])]

        if category:
            memories = [m for m in memories if m.category == category]

        # 按创建时间降序排序
        memories.sort(key=lambda x: x.created_at, reverse=True)

        return [m.to_api_dict() for m in memories]

    def add_entry(
        self,
        content: str,
        category: str = "general",
        salience: float = 0.5,
        source: str = "user_explicit",
        context: Optional[dict] = None,
        skip_dedup: bool = False,
    ) -> dict:
        """添加新记忆条目

        Args:
            content: 记忆内容
            category: 分类
            salience: 重要性评分（0.0-1.0）
            source: 来源（user_explicit/auto_extract/auto_reflection）
            context: 额外上下文
            skip_dedup: 跳过重复检测（由 consolidator 已做 LLM 决策时使用）

        Returns:
            创建的条目（API 格式）
        """
        if category not in VALID_CATEGORIES:
            category = "general"

        # 限制 salience 范围
        salience = max(0.0, min(1.0, salience))

        with self._lock:
            data = self._load_memory_json()
            memories = data.get("memories", [])

            content_stripped = content.strip()

            # 重复检测：精确匹配 + Jaccard 相似度（轻量级，无 LLM 开销）
            # consolidator 已通过 LLM 做了 ADD 决策时，跳过此检测避免矛盾
            if not skip_dedup:
                for m in memories:
                    existing = m.get("content", "").strip()
                    if existing == content_stripped:
                        return MemoryEntry.from_dict(m).to_api_dict()
                    if _jaccard_similarity(existing, content_stripped) >= self.DUPLICATE_SIMILARITY_THRESHOLD:
                        logger.info(f"检测到相似记忆，跳过添加: {content_stripped[:50]}...")
                        return MemoryEntry.from_dict(m).to_api_dict()

            # 创建新条目
            entry = MemoryEntry(
                id=MemoryEntry.generate_id(),
                category=category,
                content=content_stripped,
                salience=salience,
                source=source,
                context=context,
            )

            memories.append(entry.to_dict())
            data["memories"] = memories
            self._save_memory_json(data)

        # 通知搜索模块索引已过期
        self._invalidate_search_index()
        logger.info(f"已添加记忆条目 [{entry.id}] 到 {category}")
        return entry.to_api_dict()

    def update_entry(
        self,
        entry_id: str,
        content: Optional[str] = None,
        category: Optional[str] = None,
        salience: Optional[float] = None,
    ) -> Optional[dict]:
        """更新记忆条目

        Args:
            entry_id: 条目 ID
            content: 新内容（可选）
            category: 新分类（可选）
            salience: 新重要性（可选）

        Returns:
            更新后的条目，或 None（未找到）
        """
        result = None
        with self._lock:
            data = self._load_memory_json()
            memories = data.get("memories", [])

            for i, m in enumerate(memories):
                if m.get("id") == entry_id:
                    if content is not None:
                        m["content"] = content.strip()
                    if category is not None and category in VALID_CATEGORIES:
                        m["category"] = category
                    if salience is not None:
                        m["salience"] = max(0.0, min(1.0, salience))
                    m["last_accessed"] = datetime.now().isoformat()

                    memories[i] = m
                    data["memories"] = memories
                    self._save_memory_json(data)
                    result = MemoryEntry.from_dict(m).to_api_dict()
                    break

        # 索引失效通知放在锁外，与 add_entry 保持一致
        if result is not None:
            self._invalidate_search_index()
            logger.info(f"已更新记忆条目 [{entry_id}]")

        return result

    def delete_entry(self, entry_id: str) -> bool:
        """删除记忆条目

        Args:
            entry_id: 条目 ID

        Returns:
            是否成功删除
        """
        deleted = False
        with self._lock:
            data = self._load_memory_json()
            memories = data.get("memories", [])

            original_len = len(memories)
            memories = [m for m in memories if m.get("id") != entry_id]

            if len(memories) < original_len:
                data["memories"] = memories
                self._save_memory_json(data)
                deleted = True

        # 索引失效通知放在锁外，与 add_entry 保持一致
        if deleted:
            self._invalidate_search_index()
            logger.info(f"已删除记忆条目 [{entry_id}]")

        return deleted

    def record_access(self, entry_id: str) -> None:
        """记录条目访问（更新 last_accessed 和 access_count）"""
        with self._lock:
            data = self._load_memory_json()
            memories = data.get("memories", [])

            for m in memories:
                if m.get("id") == entry_id:
                    m["last_accessed"] = datetime.now().isoformat()
                    m["access_count"] = m.get("access_count", 1) + 1
                    self._save_memory_json(data)
                    break

    def get_rolling_summary(self) -> str:
        """获取滚动摘要"""
        data = self._load_memory_json()
        return data.get("rolling_summary", "")

    def set_rolling_summary(self, summary: str) -> None:
        """设置滚动摘要"""
        with self._lock:
            data = self._load_memory_json()
            data["rolling_summary"] = summary
            self._save_memory_json(data)

    # ============================================
    # 每日日志操作
    # ============================================

    def _daily_log_path(self, day: Optional[str] = None) -> Path:
        """获取每日日志文件路径（JSON 格式）"""
        if day is None:
            day = datetime.now().strftime("%Y-%m-%d")
        return self.logs_dir / f"{day}.json"

    def append_daily_log(
        self,
        content: str,
        day: Optional[str] = None,
        log_type: str = "event",
        category: Optional[str] = None,
        tool: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """向每日日志追加条目

        Args:
            content: 日志内容
            day: 日期（默认今天）
            log_type: 类型（event/auto_extract/reflection）
            category: 分类（用于 auto_extract）
            tool: 工具名（用于 reflection）
            error: 错误信息（用于 reflection）
        """
        path = self._daily_log_path(day)
        timestamp = datetime.now().strftime("%H:%M:%S")

        # 日志文件的 read-modify-write 需持锁保护，防止并发写入丢失数据
        # （auto_extract、reflection、用户纠正等多条路径可能同时触发）
        with self._lock:
            # 加载或创建日志
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    daily_log = DailyLog.from_dict(data)
                except Exception:
                    daily_log = DailyLog(date=day or datetime.now().strftime("%Y-%m-%d"))
            else:
                daily_log = DailyLog(date=day or datetime.now().strftime("%Y-%m-%d"))

            # 添加条目
            entry = DailyLogEntry(
                time=timestamp,
                type=log_type,
                content=content,
                category=category,
                tool=tool,
                error=error,
            )
            daily_log.entries.append(entry)

            # 保存
            path.write_text(
                json.dumps(daily_log.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        logger.info(f"已追加到每日日志: {path.name}")

    def read_daily_log(self, day: Optional[str] = None) -> str:
        """读取每日日志内容（返回人类可读格式）"""
        path = self._daily_log_path(day)

        if not path.exists():
            # 兼容旧版 .md 格式
            md_path = self.logs_dir / f"{day or datetime.now().strftime('%Y-%m-%d')}.md"
            if md_path.exists():
                return md_path.read_text(encoding="utf-8")
            return ""

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            daily_log = DailyLog.from_dict(data)
        except Exception:
            return ""

        # 格式化为人类可读格式
        lines = [f"# Daily Log - {daily_log.date}\n"]
        for entry in daily_log.entries:
            prefix = ""
            if entry.type == "auto_extract" and entry.category:
                prefix = f"[auto] [{entry.category}] "
            elif entry.type == "reflection" and entry.tool:
                prefix = f"[reflection] [{entry.tool}] "

            lines.append(f"- [{entry.time[:5]}] {prefix}{entry.content}")

        if daily_log.summary:
            lines.append(f"\n## 摘要\n{daily_log.summary}")

        return "\n".join(lines)

    def delete_daily_log(self, day: str) -> bool:
        """删除每日日志文件"""
        path = self._daily_log_path(day)
        if path.exists():
            path.unlink()
            logger.info(f"已删除每日日志: {path.name}")
            return True

        # 兼容旧版 .md 格式
        md_path = self.logs_dir / f"{day}.md"
        if md_path.exists():
            md_path.unlink()
            logger.info(f"已删除每日日志: {md_path.name}")
            return True

        return False

    def list_daily_logs(self) -> list[dict]:
        """列出所有每日日志文件及元数据"""
        logs = []
        if not self.logs_dir.exists():
            return logs

        # 收集 .json 和 .md 文件
        seen_dates = set()

        for f in sorted(self.logs_dir.glob("*.json"), reverse=True):
            if not re.match(r"\d{4}-\d{2}-\d{2}", f.stem):
                continue
            seen_dates.add(f.stem)
            stat = f.stat()
            logs.append({
                "date": f.stem,
                "path": f"memory/logs/{f.name}",
                "size": stat.st_size,
            })

        # 兼容旧版 .md 文件
        for f in sorted(self.logs_dir.glob("*.md"), reverse=True):
            if not re.match(r"\d{4}-\d{2}-\d{2}", f.stem):
                continue
            if f.stem in seen_dates:
                continue  # 已有 JSON 版本
            stat = f.stat()
            logs.append({
                "date": f.stem,
                "path": f"memory/logs/{f.name}",
                "size": stat.st_size,
            })

        # 按日期降序排序
        logs.sort(key=lambda x: x["date"], reverse=True)
        return logs

    def get_daily_context(self, num_days: Optional[int] = None) -> str:
        """获取近期每日日志，用于注入 System Prompt"""
        if num_days is None:
            num_days = settings.memory_daily_log_days

        parts = []
        today = datetime.now()

        for i in range(num_days):
            day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            content = self.read_daily_log(day)
            if content:
                label = "今天" if i == 0 else f"{i}天前" if i > 1 else "昨天"
                parts.append(f"### {label} ({day})\n{content}")

        return "\n\n".join(parts)

    # ============================================
    # 程序性记忆（Procedural Memory）
    # ============================================

    def get_procedural_memories(self, tool: Optional[str] = None) -> list[dict]:
        """获取程序性记忆（工具使用经验）

        Args:
            tool: 可选的工具名过滤

        Returns:
            程序性记忆列表
        """
        entries = self.get_entries(category="procedural")

        if tool:
            # 一次性加载 memory.json，避免循环内重复读取
            data = self._load_memory_json()
            # 构建 ID → context 映射
            context_map = {
                m.get("id"): m.get("context", {})
                for m in data.get("memories", [])
            }
            # 过滤特定工具的经验
            filtered = []
            for e in entries:
                ctx = context_map.get(e["entry_id"], {})
                if ctx and ctx.get("tool") == tool:
                    filtered.append(e)
            return filtered

        return entries

    def _invalidate_search_index(self) -> None:
        """通知搜索模块记忆索引已过期，下次搜索时懒加载重建"""
        try:
            from memory.search import invalidate_memory_index
            invalidate_memory_index()
        except ImportError:
            pass

    def add_procedural_memory(
        self,
        content: str,
        tool: str,
        error_type: Optional[str] = None,
        session_id: Optional[str] = None,
        salience: float = 0.8,
    ) -> dict:
        """添加程序性记忆（工具使用经验）

        Args:
            content: 经验描述
            tool: 工具名
            error_type: 错误类型（可选）
            session_id: 来源会话（可选）
            salience: 重要性（默认较高）

        Returns:
            创建的条目
        """
        context = {
            "tool": tool,
        }
        if error_type:
            context["error_type"] = error_type
        if session_id:
            context["learned_from"] = session_id

        return self.add_entry(
            content=content,
            category="procedural",
            salience=salience,
            source="auto_reflection",
            context=context,
        )

    # ============================================
    # 统计
    # ============================================

    def get_stats(self) -> dict:
        """获取记忆统计信息"""
        data = self._load_memory_json()
        memories = [MemoryEntry.from_dict(m) for m in data.get("memories", [])]
        logs = self.list_daily_logs()

        # 按分类计数
        category_counts = {}
        for cat in VALID_CATEGORIES:
            category_counts[cat] = sum(1 for m in memories if m.category == cat)

        # 平均重要性
        avg_salience = (
            sum(m.salience for m in memories) / len(memories)
            if memories else 0
        )

        memory_size = self.memory_file.stat().st_size if self.memory_file.exists() else 0

        return {
            "total_entries": len(memories),
            "category_counts": category_counts,
            "avg_salience": round(avg_salience, 2),
            "daily_logs_count": len(logs),
            "memory_file_size": memory_size,
            "daily_log_days": settings.memory_daily_log_days,
            "auto_extract_enabled": settings.memory_auto_extract,
            "version": data.get("version", 1),
        }

    # ============================================
    # 自动提取
    # ============================================

    async def auto_extract(self, messages: list[dict]) -> None:
        """从近期消息中自动提取关键信息

        委托给 extractor.py 的 process_message_for_memory 实现，
        支持 JSON 格式输出、salience 评分、显式记忆请求检测。
        提取结果写入每日日志。
        """
        if not settings.memory_auto_extract:
            return

        try:
            from memory.extractor import process_message_for_memory

            # 取最近一条用户消息用于显式检测
            last_user_msg = ""
            for msg in reversed(messages):
                if msg.get("role") == "user" and msg.get("content"):
                    last_user_msg = msg["content"]
                    break

            if not last_user_msg and not messages:
                return

            # 使用 extractor 的综合提取（显式检测 + 隐式提取）
            extracted = await process_message_for_memory(
                message=last_user_msg,
                role="user",
                session_messages=messages,
            )

            if not extracted:
                return

            for item in extracted:
                cat = item.get("category", "general")
                content = item.get("content", "")
                salience = item.get("salience", 0.5)

                if not content:
                    continue

                # 写入每日日志（带分类和类型）
                self.append_daily_log(
                    content=content,
                    log_type="auto_extract",
                    category=cat,
                )

                # 高重要性（>=0.8）的记忆同时写入长期记忆
                # 避免显式记忆请求（如"记住..."）只停留在日志中等 30 天才归档提升
                if salience >= 0.8:
                    try:
                        self.add_entry(
                            content=content,
                            category=cat,
                            salience=salience,
                            source="auto_extract",
                        )
                    except Exception as e:
                        logger.warning(f"自动提取写入长期记忆失败: {e}")

                logger.info(f"自动提取: [{cat}] (salience={salience:.1f}) {content[:50]}...")

        except Exception as e:
            logger.error(f"自动提取失败: {e}")


# 单例实例
memory_manager = MemoryManager()
