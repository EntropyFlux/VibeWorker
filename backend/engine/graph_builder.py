"""图构建器 — 根据配置组装 StateGraph。

根据 graph_config.yaml 配置控制哪些节点添加、边如何连接。
编译后的图通过内容指纹缓存，配置不变时复用。

内存管理增强：
- MemorySaver 的 checkpoint 数据会随会话增长而无限累积
- 添加定期清理机制，限制每个 thread 最多保留的 checkpoint 数量
"""
import hashlib
import json
import logging
import time
from functools import lru_cache
from typing import Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from engine.config_loader import get_node_config, get_settings, load_graph_config
from engine.edges import (
    route_after_agent,
    route_after_approval,
    route_after_plan_gate,
    route_after_replanner,
)
from engine.nodes import (
    agent_node,
    approval_node,
    executor_pre_node,
    executor_node,
    plan_gate_node,
    replanner_node,
    summarizer_node,
)
from engine.state import AgentState

logger = logging.getLogger(__name__)

# 图缓存：fingerprint → 编译后的图
_graph_cache: dict[str, tuple] = {}

# 全局 checkpointer（用于 interrupt/resume）
_checkpointer = MemorySaver()

# Checkpoint 清理配置
_CHECKPOINT_MAX_PER_THREAD = 20  # 每个 thread 最多保留的 checkpoint 数量
_CHECKPOINT_CLEANUP_INTERVAL = 300  # 清理间隔（秒）
_last_checkpoint_cleanup = 0.0


def cleanup_old_checkpoints() -> int:
    """清理旧的 checkpoint 数据，防止内存无限增长。

    MemorySaver 使用内部的 storage dict 存储所有 checkpoint。
    每个 thread_id 可能有多个 checkpoint（每次节点转换都会创建）。
    这里清理超过限制数量的旧 checkpoint。

    Returns:
        清理的 checkpoint 数量
    """
    global _last_checkpoint_cleanup

    now = time.time()
    if now - _last_checkpoint_cleanup < _CHECKPOINT_CLEANUP_INTERVAL:
        return 0

    _last_checkpoint_cleanup = now
    cleaned = 0

    try:
        # MemorySaver 的内部存储结构：storage = {(thread_id, checkpoint_ns, checkpoint_id): checkpoint_data}
        # 我们需要按 thread_id 分组并保留最新的
        storage = getattr(_checkpointer, "storage", {})
        if not storage:
            return 0

        # 按 thread_id 分组
        by_thread: dict[str, list[tuple]] = {}
        for key in list(storage.keys()):
            if isinstance(key, tuple) and len(key) >= 1:
                thread_id = key[0]
                by_thread.setdefault(thread_id, []).append(key)

        # 对每个 thread，只保留最新的 N 个 checkpoint
        for thread_id, keys in by_thread.items():
            if len(keys) <= _CHECKPOINT_MAX_PER_THREAD:
                continue

            # 按 checkpoint_id 排序（通常是时间戳格式）
            sorted_keys = sorted(keys, key=lambda k: k[2] if len(k) > 2 else "", reverse=True)
            keys_to_remove = sorted_keys[_CHECKPOINT_MAX_PER_THREAD:]

            for key in keys_to_remove:
                try:
                    del storage[key]
                    cleaned += 1
                except KeyError:
                    pass

        if cleaned > 0:
            logger.info(f"已清理 {cleaned} 个旧 checkpoint")

    except Exception as e:
        logger.debug(f"Checkpoint 清理时出错（非致命）: {e}")

    return cleaned


def build_graph(graph_config: dict):
    """根据配置构建 StateGraph 并编译。

    Args:
        graph_config: 从 config_loader 加载的完整配置

    Returns:
        编译后的 CompiledGraph
    """
    nodes_cfg = graph_config.get("graph", {}).get("nodes", {})
    settings_cfg = get_settings(graph_config)

    planner_enabled = nodes_cfg.get("planner", {}).get("enabled", True)
    approval_enabled = nodes_cfg.get("approval", {}).get("enabled", False)
    replanner_enabled = nodes_cfg.get("replanner", {}).get("enabled", True)
    summarizer_enabled = nodes_cfg.get("summarizer", {}).get("enabled", True)

    graph = StateGraph(AgentState)

    # ========== 添加节点 ==========
    graph.add_node("agent", agent_node)

    if planner_enabled:
        graph.add_node("plan_gate", plan_gate_node)

        if approval_enabled:
            graph.add_node("approval", approval_node)

        graph.add_node("executor_pre", executor_pre_node)
        graph.add_node("executor", executor_node)

        if replanner_enabled:
            graph.add_node("replanner", replanner_node)

        if summarizer_enabled:
            graph.add_node("summarizer", summarizer_node)

    # ========== 入口 ==========
    graph.set_entry_point("agent")

    # ========== 添加边 ==========

    if planner_enabled:
        # agent → plan_gate | END
        graph.add_conditional_edges("agent", route_after_agent, {
            "plan_gate": "plan_gate",
            END: END,
        })

        # executor_pre → executor（始终连接）
        graph.add_edge("executor_pre", "executor")

        # plan_gate → approval | executor_pre
        if approval_enabled:
            def _route_plan_gate(state):
                return route_after_plan_gate(state, approval_enabled=True)

            graph.add_conditional_edges("plan_gate", _route_plan_gate, {
                "approval": "approval",
                "executor_pre": "executor_pre",
            })

            # approval → executor_pre | agent
            graph.add_conditional_edges("approval", route_after_approval, {
                "executor_pre": "executor_pre",
                "agent": "agent",
            })
        else:
            graph.add_edge("plan_gate", "executor_pre")

        if replanner_enabled:
            # executor → replanner
            graph.add_edge("executor", "replanner")

            if summarizer_enabled:
                # replanner → executor_pre | summarizer
                graph.add_conditional_edges("replanner", route_after_replanner, {
                    "executor_pre": "executor_pre",
                    "summarizer": "summarizer",
                })
                # summarizer → agent（回到主循环）
                graph.add_edge("summarizer", "agent")
            else:
                # replanner → executor_pre | END
                graph.add_conditional_edges("replanner", route_after_replanner, {
                    "executor_pre": "executor_pre",
                    "summarizer": END,  # summarizer 禁用时直连 END
                })
        else:
            # 无 replanner：executor 自行判断是否完成
            if summarizer_enabled:
                def _route_executor_no_replanner(state: AgentState) -> str:
                    """无 replanner 时的 executor 路由。"""
                    plan_data = state.get("plan_data")
                    if not plan_data:
                        return "summarizer"
                    step_index = state.get("current_step_index", 0)
                    total_steps = len(plan_data.get("steps", []))
                    max_steps = nodes_cfg.get("executor", {}).get("max_steps", 8)
                    if step_index >= total_steps or step_index >= max_steps:
                        return "summarizer"
                    return "executor_pre"

                graph.add_conditional_edges("executor", _route_executor_no_replanner, {
                    "executor_pre": "executor_pre",
                    "summarizer": "summarizer",
                })
                graph.add_edge("summarizer", "agent")
            else:
                def _route_executor_minimal(state: AgentState) -> str:
                    """最简模式的 executor 路由。"""
                    plan_data = state.get("plan_data")
                    if not plan_data:
                        return END
                    step_index = state.get("current_step_index", 0)
                    total_steps = len(plan_data.get("steps", []))
                    max_steps = nodes_cfg.get("executor", {}).get("max_steps", 8)
                    if step_index >= total_steps or step_index >= max_steps:
                        return END
                    return "executor_pre"

                graph.add_conditional_edges("executor", _route_executor_minimal, {
                    "executor_pre": "executor_pre",
                    END: END,
                })
    else:
        # planner 禁用 → agent 直连 END
        graph.add_edge("agent", END)

    # ========== 编译 ==========
    recursion_limit = settings_cfg.get("recursion_limit", 100)
    compiled = graph.compile(
        checkpointer=_checkpointer,
    )

    logger.info("StateGraph 已构建: planner=%s, approval=%s, replanner=%s, summarizer=%s",
                planner_enabled, approval_enabled, replanner_enabled, summarizer_enabled)

    return compiled


def get_or_build_graph(graph_config: dict):
    """获取或构建编译后的图（带指纹缓存）。"""
    # 定期清理旧 checkpoint，防止内存无限增长
    cleanup_old_checkpoints()

    fp = _config_fingerprint(graph_config)
    if fp not in _graph_cache:
        compiled = build_graph(graph_config)
        _graph_cache[fp] = compiled
        logger.debug("图已缓存，指纹: %s", fp)
    return _graph_cache[fp]


def _config_fingerprint(graph_config: dict) -> str:
    """根据配置内容生成 SHA256 短指纹。"""
    raw = json.dumps(graph_config, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def invalidate_graph_cache() -> None:
    """清除图缓存。配置变更后应调用此函数。"""
    _graph_cache.clear()
    logger.info("图缓存已清除")
