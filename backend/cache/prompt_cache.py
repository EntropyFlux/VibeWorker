"""
Prompt cache for System Prompt concatenation results.
"""

import hashlib
import json
import logging
from typing import Optional
from pathlib import Path

from .memory_cache import MemoryCache
from .disk_cache import DiskCache
from config import settings

logger = logging.getLogger(__name__)


class PromptCache:
    """
    Two-tier cache for System Prompt concatenation results.

    Cache key is based on workspace file modification times,
    so cache automatically invalidates when files change.
    """

    def __init__(self):
        """Initialize Prompt cache with L1 + L2."""
        self.l1 = MemoryCache(
            max_size=settings.cache_max_memory_items,
            default_ttl=settings.prompt_cache_ttl,
        )
        self.l2 = DiskCache(
            cache_dir=settings.cache_dir,
            cache_type="prompt",
            default_ttl=settings.prompt_cache_ttl,
            max_size_mb=settings.cache_max_disk_size_mb,
        )

    def _get_workspace_files_version(self) -> dict:
        """
        Get version info for all workspace files.

        Returns:
            Dict mapping file paths to modification times
        """
        files_version = {}

        try:
            workspace_files = [
                settings.workspace_dir / "SOUL.md",
                settings.workspace_dir / "IDENTITY.md",
                settings.workspace_dir / "USER.md",
                settings.workspace_dir / "AGENTS.md",
            ]

            # 监听 memory.json（v2 记忆系统的核心文件）
            memory_json = settings.memory_dir / "memory.json"
            if memory_json.exists():
                workspace_files.append(memory_json)

            # 监听每日日志文件（.json 格式）用于缓存失效
            from datetime import datetime, timedelta
            logs_dir = settings.memory_dir / "logs"
            if logs_dir.exists():
                today = datetime.now()
                for i in range(settings.memory_daily_log_days):
                    day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                    log_file = logs_dir / f"{day}.json"
                    if log_file.exists():
                        workspace_files.append(log_file)

            # 监控 skills 目录变化（新增/删除/修改 skill）
            skills_dir = settings.skills_dir
            if skills_dir.exists():
                # 记录 skills 目录本身的 mtime（新增/删除子目录会改变）
                files_version[str(skills_dir)] = skills_dir.stat().st_mtime
                # 记录每个 SKILL.md 文件的 mtime
                for skill_subdir in skills_dir.iterdir():
                    if skill_subdir.is_dir():
                        skill_md = skill_subdir / "SKILL.md"
                        if skill_md.exists():
                            workspace_files.append(skill_md)

            for file_path in workspace_files:
                if file_path.exists():
                    files_version[str(file_path)] = file_path.stat().st_mtime

        except Exception as e:
            logger.warning(f"Failed to get workspace files version: {e}")

        return files_version

    def _compute_cache_key(self) -> str:
        """
        Compute cache key based on workspace file versions.

        Returns:
            SHA256 hash of file versions
        """
        files_version = self._get_workspace_files_version()
        version_str = json.dumps(files_version, sort_keys=True)
        return hashlib.sha256(version_str.encode("utf-8")).hexdigest()

    def get_cached_prompt(self) -> Optional[str]:
        """
        Get cached System Prompt.

        Returns:
            Cached prompt if exists, None otherwise
        """
        if not settings.enable_prompt_cache:
            return None

        cache_key = self._compute_cache_key()

        # Try L1 first
        cached = self.l1.get(cache_key)
        if cached is not None:
            logger.debug("Prompt cache L1 hit")
            return cached

        # Try L2
        cached = self.l2.get(cache_key)
        if cached is not None:
            logger.debug("Prompt cache L2 hit")
            # Promote to L1
            self.l1.set(cache_key, cached)
            return cached

        logger.debug("Prompt cache miss")
        return None

    def cache_prompt(self, prompt: str) -> None:
        """
        Cache System Prompt.

        Args:
            prompt: System prompt to cache
        """
        if not settings.enable_prompt_cache:
            return

        cache_key = self._compute_cache_key()

        # Store in both L1 and L2
        self.l1.set(cache_key, prompt)
        self.l2.set(cache_key, prompt)

        logger.debug("System prompt cached")

    def clear(self) -> dict:
        """
        Clear all Prompt cache.

        Returns:
            Dict with clear counts
        """
        l1_count = self.l1.clear()
        l2_count = self.l2.clear()

        return {
            "l1_cleared": l1_count,
            "l2_cleared": l2_count,
        }

    def get_stats(self) -> dict:
        """Get Prompt cache statistics."""
        return {
            "enabled": settings.enable_prompt_cache,
            "ttl": settings.prompt_cache_ttl,
            "l1": self.l1.get_stats(),
            "l2": self.l2.get_stats(),
        }
