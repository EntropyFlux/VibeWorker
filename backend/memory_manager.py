"""Memory Manager - Central hub for VibeWorker's memory system.

Manages both long-term memory (MEMORY.md) and daily logs (memory/logs/YYYY-MM-DD.md).
Provides structured entry management, daily log operations, and statistics.
"""
import hashlib
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# Category definitions
VALID_CATEGORIES = ["preferences", "facts", "tasks", "reflections", "general"]

CATEGORY_LABELS = {
    "preferences": "用户偏好",
    "facts": "重要事实",
    "tasks": "任务备忘",
    "reflections": "反思日志",
    "general": "通用记忆",
}

CATEGORY_HEADERS = {
    "preferences": "## 用户偏好",
    "facts": "## 重要事实",
    "tasks": "## 任务备忘",
    "reflections": "## 反思日志",
    "general": "## 通用记忆",
}


class MemoryEntry:
    """A single memory entry."""

    def __init__(self, content: str, category: str, timestamp: str, entry_id: str = ""):
        self.content = content
        self.category = category
        self.timestamp = timestamp
        self.entry_id = entry_id or self._generate_id(timestamp, content)

    @staticmethod
    def _generate_id(timestamp: str, content: str) -> str:
        raw = f"{timestamp}:{content}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "content": self.content,
            "category": self.category,
            "timestamp": self.timestamp,
        }


class MemoryManager:
    """Central memory management class."""

    def __init__(self):
        self.memory_dir = settings.memory_dir
        self.logs_dir = settings.memory_dir / "logs"
        self.memory_file = settings.memory_dir / "MEMORY.md"
        # Ensure directories exist
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    # ============================================
    # MEMORY.md Operations
    # ============================================

    def read_memory(self) -> str:
        """Read the entire MEMORY.md file."""
        if not self.memory_file.exists():
            return ""
        return self.memory_file.read_text(encoding="utf-8")

    def get_entries(self, category: Optional[str] = None) -> list[dict]:
        """Parse MEMORY.md and return structured entries.

        Each entry is a bullet point line: `- [YYYY-MM-DD] content` or `- [YYYY-MM-DD][id] content`
        """
        content = self.read_memory()
        if not content:
            return []

        entries = []
        current_category = "general"

        for line in content.split("\n"):
            stripped = line.strip()

            # Detect category headers
            for cat, header in CATEGORY_HEADERS.items():
                if stripped.startswith(header):
                    current_category = cat
                    break

            # Parse entry lines: `- [YYYY-MM-DD] content` or `- [YYYY-MM-DD][id] content`
            match = re.match(
                r"^-\s+\[(\d{4}-\d{2}-\d{2})\](?:\[([a-f0-9]+)\])?\s*(.+)$",
                stripped,
            )
            if match:
                timestamp = match.group(1)
                entry_id = match.group(2) or ""
                entry_content = match.group(3)

                entry = MemoryEntry(
                    content=entry_content,
                    category=current_category,
                    timestamp=timestamp,
                    entry_id=entry_id,
                )
                # Generate ID if not present
                if not entry.entry_id:
                    entry.entry_id = entry._generate_id(timestamp, entry_content)

                if category is None or current_category == category:
                    entries.append(entry.to_dict())

        return entries

    def add_entry(self, content: str, category: str = "general") -> dict:
        """Add a new entry to MEMORY.md under the corresponding category section.

        Returns the created MemoryEntry dict. Deduplicates by content similarity.
        """
        if category not in VALID_CATEGORIES:
            category = "general"

        today = datetime.now().strftime("%Y-%m-%d")
        entry = MemoryEntry(content=content, category=category, timestamp=today)

        # Check for duplicates
        existing = self.get_entries(category)
        for e in existing:
            if e["content"].strip() == content.strip():
                return e  # Already exists

        # Read current content
        memory_content = self.read_memory()

        header = CATEGORY_HEADERS[category]
        new_line = f"- [{today}][{entry.entry_id}] {content}"

        if header in memory_content:
            # Find the section and insert after placeholder or last entry
            lines = memory_content.split("\n")
            new_lines = []
            found_section = False
            inserted = False

            for i, line in enumerate(lines):
                new_lines.append(line)
                if line.strip().startswith(header):
                    found_section = True
                    continue
                if found_section and not inserted:
                    # Remove placeholder if present
                    if line.strip() == "_（暂无记录）_":
                        new_lines[-1] = new_line
                        inserted = True
                    elif not line.strip().startswith("- [") and not line.strip() == "":
                        # We've passed the section entries, insert before this line
                        new_lines.insert(len(new_lines) - 1, new_line)
                        inserted = True
                    elif line.strip() == "" and i + 1 < len(lines) and lines[i + 1].strip().startswith("##"):
                        # End of section (empty line before next header)
                        new_lines.insert(len(new_lines) - 1, new_line)
                        inserted = True

            if found_section and not inserted:
                new_lines.append(new_line)

            memory_content = "\n".join(new_lines)
        else:
            # Section doesn't exist, append it
            memory_content = memory_content.rstrip() + f"\n\n{header}\n{new_line}\n"

        self.memory_file.write_text(memory_content, encoding="utf-8")
        logger.info(f"Added memory entry [{entry.entry_id}] to {category}")
        return entry.to_dict()

    def delete_entry(self, entry_id: str) -> bool:
        """Delete a memory entry by its ID."""
        content = self.read_memory()
        if not content:
            return False

        lines = content.split("\n")
        new_lines = []
        deleted = False

        for line in lines:
            # Check if line contains this entry ID
            if f"[{entry_id}]" in line and line.strip().startswith("- ["):
                deleted = True
                continue
            # Also try matching by generated ID
            match = re.match(
                r"^-\s+\[(\d{4}-\d{2}-\d{2})\](?:\[([a-f0-9]+)\])?\s*(.+)$",
                line.strip(),
            )
            if match and not match.group(2):
                ts = match.group(1)
                cnt = match.group(3)
                gen_id = MemoryEntry._generate_id(ts, cnt)
                if gen_id == entry_id:
                    deleted = True
                    continue
            new_lines.append(line)

        if deleted:
            self.memory_file.write_text("\n".join(new_lines), encoding="utf-8")
            logger.info(f"Deleted memory entry [{entry_id}]")

        return deleted

    # ============================================
    # Daily Log Operations
    # ============================================

    def _daily_log_path(self, day: Optional[str] = None) -> Path:
        """Get the path for a daily log file."""
        if day is None:
            day = datetime.now().strftime("%Y-%m-%d")
        return self.logs_dir / f"{day}.md"

    def append_daily_log(self, content: str, day: Optional[str] = None) -> None:
        """Append content to today's (or specified day's) daily log."""
        path = self._daily_log_path(day)
        timestamp = datetime.now().strftime("%H:%M")

        if not path.exists():
            day_str = day or datetime.now().strftime("%Y-%m-%d")
            path.write_text(
                f"# Daily Log - {day_str}\n\n", encoding="utf-8"
            )

        existing = path.read_text(encoding="utf-8")
        existing += f"- [{timestamp}] {content}\n"
        path.write_text(existing, encoding="utf-8")
        logger.info(f"Appended to daily log: {path.name}")

    def read_daily_log(self, day: Optional[str] = None) -> str:
        """Read a daily log file."""
        path = self._daily_log_path(day)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def list_daily_logs(self) -> list[dict]:
        """List all daily log files with metadata."""
        logs = []
        if not self.logs_dir.exists():
            return logs

        for f in sorted(self.logs_dir.glob("*.md"), reverse=True):
            name = f.stem  # e.g., "2026-02-15"
            # Validate format
            if not re.match(r"\d{4}-\d{2}-\d{2}", name):
                continue
            stat = f.stat()
            logs.append({
                "date": name,
                "path": f"memory/logs/{f.name}",
                "size": stat.st_size,
            })

        return logs

    def get_daily_context(self, num_days: Optional[int] = None) -> str:
        """Get recent daily logs for System Prompt injection.

        Returns today + yesterday (or configurable number of days) logs.
        """
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
    # Statistics
    # ============================================

    def get_stats(self) -> dict:
        """Get memory statistics."""
        entries = self.get_entries()
        logs = self.list_daily_logs()

        # Count by category
        category_counts = {}
        for cat in VALID_CATEGORIES:
            category_counts[cat] = sum(1 for e in entries if e["category"] == cat)

        memory_size = self.memory_file.stat().st_size if self.memory_file.exists() else 0

        return {
            "total_entries": len(entries),
            "category_counts": category_counts,
            "daily_logs_count": len(logs),
            "memory_file_size": memory_size,
            "daily_log_days": settings.memory_daily_log_days,
            "auto_extract_enabled": settings.memory_auto_extract,
        }

    # ============================================
    # Auto Extraction (Phase 6)
    # ============================================

    async def auto_extract(self, messages: list[dict]) -> None:
        """Automatically extract key information from recent messages.

        Takes last 3 rounds (6 messages), uses lightweight LLM to extract
        preferences/facts/tasks, writes to daily log with [auto] prefix.
        """
        if not settings.memory_auto_extract:
            return

        try:
            # Take last 6 messages
            recent = messages[-6:] if len(messages) > 6 else messages
            if not recent:
                return

            # Build conversation text
            conversation = ""
            for msg in recent:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if content:
                    conversation += f"{role}: {content[:500]}\n"

            if not conversation.strip():
                return

            from graph.agent import create_llm
            llm = create_llm()

            prompt = f"""分析以下对话，提取值得记住的关键信息。只提取确定性的事实和偏好，不要猜测。

如果没有值得记录的信息，返回"无"。

如果有，每条一行，格式：`类别|内容`
可用类别：preferences（偏好）、facts（事实）、tasks（任务）

对话内容：
{conversation}

提取结果："""

            response = await llm.ainvoke(prompt)
            result = response.content.strip()

            if result == "无" or not result:
                return

            for line in result.split("\n"):
                line = line.strip()
                if "|" not in line:
                    continue
                parts = line.split("|", 1)
                if len(parts) != 2:
                    continue
                cat = parts[0].strip().lower()
                content = parts[1].strip()
                if not content:
                    continue

                # Write to daily log with [auto] prefix
                self.append_daily_log(f"[auto] [{cat}] {content}")
                logger.info(f"Auto-extracted: [{cat}] {content[:50]}...")

        except Exception as e:
            logger.error(f"Auto-extraction failed: {e}")


# Singleton instance
memory_manager = MemoryManager()
