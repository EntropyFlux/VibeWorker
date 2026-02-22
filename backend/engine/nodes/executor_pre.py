"""Executor Pre 节点 — 步骤执行前置节点。

轻量节点，仅发送 plan_updated(running) 事件。
独立于 executor 节点，确保 running 事件在步骤真正执行之前到达前端，
避免 running 和 completed 事件同批返回导致的状态跳跃问题。
"""
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from engine.state import AgentState

logger = logging.getLogger(__name__)


async def executor_pre_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """步骤执行前置节点。

    仅标记当前步骤为 running 并发送 plan_updated 事件。
    该节点有独立的 on_chain_end 回调，因此 running 事件
    会在 executor 开始执行前就到达前端。
    """
    plan_data = state.get("plan_data")
    if not plan_data:
        return {}

    steps = plan_data.get("steps", [])
    step_index = state.get("current_step_index", 0)

    if step_index >= len(steps):
        return {}

    step = steps[step_index]
    step_id = step["id"] if isinstance(step, dict) else step_index + 1
    plan_id = plan_data.get("plan_id", "")

    sid = state.get("session_id", "unknown")
    step_title = step["title"] if isinstance(step, dict) else str(step)
    logger.info("[%s] ExecutorPre: 标记步骤 %d/%d 为 running - %s",
                sid, step_index + 1, len(steps), step_title)

    return {
        "pending_events": [{
            "type": "plan_updated",
            "plan_id": plan_id,
            "step_id": step_id,
            "status": "running",
        }],
    }
