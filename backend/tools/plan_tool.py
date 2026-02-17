"""Plan Tool - Create and update execution plans for complex tasks."""
import asyncio
import logging
from typing import Optional, Callable
from uuid import uuid4

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Module-level SSE callback for plan events (same pattern as SecurityGate)
_sse_plan_callback: Optional[Callable] = None

# Latest plan data storage for Phase 2 handoff
_latest_plan: Optional[dict] = None


def get_latest_plan() -> Optional[dict]:
    """Get and consume the latest plan created by plan_create tool.

    Returns the plan data and clears it so it's only consumed once.
    """
    global _latest_plan
    plan = _latest_plan
    _latest_plan = None
    return plan


def set_plan_sse_callback(callback: Optional[Callable]) -> None:
    """Set the SSE callback for plan events."""
    global _sse_plan_callback
    _sse_plan_callback = callback


def get_plan_sse_callback() -> Optional[Callable]:
    """Get the current plan SSE callback."""
    return _sse_plan_callback


def _send_plan_event(event_data: dict) -> None:
    """Send a plan event through the SSE callback (thread-safe)."""
    callback = get_plan_sse_callback()
    if callback is None:
        return
    try:
        # Tools run in thread pool, so we need thread-safe scheduling
        loop = _event_loop or asyncio.get_event_loop()
        loop.call_soon_threadsafe(asyncio.ensure_future, callback(event_data))
    except RuntimeError:
        # No event loop available — try direct approach
        try:
            asyncio.run(callback(event_data))
        except Exception:
            pass


# Store reference to the main event loop (set from app.py)
_event_loop: asyncio.AbstractEventLoop = None  # type: ignore


def set_plan_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Store reference to the main async event loop for thread-safe callbacks."""
    global _event_loop
    _event_loop = loop


@tool
def plan_create(title: str, steps: list) -> str:
    """仅当任务确实需要 3 个以上步骤且涉及多个不同工具协作时，才调用此工具创建执行计划。简单问答、闲聊、单步工具调用等绝对不要使用此工具。

    Args:
        title: 计划的简短标题。
        steps: 按执行顺序排列的步骤描述列表（字符串数组），每个步骤约 10 字。例如 ["读取文件", "分析内容", "保存结果"]
    """
    if not title or not title.strip():
        return "Error: Plan title cannot be empty."

    if not steps or len(steps) == 0:
        return "Error: Plan must have at least one step."

    # Normalize steps: LLM may send dicts like {"step": "..."} instead of strings
    normalized = []
    for s in steps:
        if isinstance(s, dict):
            text = s.get("step") or s.get("title") or s.get("description") or str(next(iter(s.values()), ""))
        else:
            text = str(s)
        normalized.append(text.strip())

    plan_id = uuid4().hex[:8]
    plan = {
        "plan_id": plan_id,
        "title": title.strip(),
        "steps": [
            {"id": i + 1, "title": s, "status": "pending"}
            for i, s in enumerate(normalized)
        ],
    }

    # Store plan data for Phase 2 handoff
    global _latest_plan
    _latest_plan = plan

    _send_plan_event({"type": "plan_created", "plan": plan})

    return f"Plan created: plan_id={plan_id}, {len(steps)} steps. System will now auto-execute each step."


@tool
def plan_update(plan_id: str, step_id: int, status: str) -> str:
    """更新执行计划中某个步骤的状态。执行步骤前必须先标记为 running，完成后标记为 completed 或 failed。

    Args:
        plan_id: plan_create 返回的计划 ID。
        step_id: 要更新的步骤编号（从 1 开始）。
        status: 新状态，必须是 pending、running、completed、failed 之一。
    """
    valid_statuses = {"pending", "running", "completed", "failed"}
    if status not in valid_statuses:
        return f"Error: Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}"

    # Auto-complete previous steps when marking a new step as running
    if status == "running" and step_id > 1:
        for prev_id in range(1, step_id):
            _send_plan_event({
                "type": "plan_updated",
                "plan_id": plan_id,
                "step_id": prev_id,
                "status": "completed",
            })

    _send_plan_event({
        "type": "plan_updated",
        "plan_id": plan_id,
        "step_id": step_id,
        "status": status,
    })

    return f"Step {step_id} -> {status}"


def send_plan_revised_event(plan_id: str, revised_steps: list[dict], keep_completed: int, reason: str = "") -> None:
    """Send a plan_revised SSE event from the Replanner node.

    Args:
        plan_id: The plan ID being revised.
        revised_steps: New steps list (each dict with id, title, status).
        keep_completed: Number of completed steps kept from the original plan.
        reason: Why the plan was revised.
    """
    _send_plan_event({
        "type": "plan_revised",
        "plan_id": plan_id,
        "revised_steps": revised_steps,
        "keep_completed": keep_completed,
        "reason": reason,
    })


def send_plan_created_event(plan: dict) -> None:
    """Send a plan_created SSE event directly (used by task-mode Planner node).

    Args:
        plan: Plan dict with plan_id, title, steps.
    """
    _send_plan_event({"type": "plan_created", "plan": plan})


def send_plan_updated_event(plan_id: str, step_id: int, status: str) -> None:
    """Send a plan_updated SSE event directly (used by task-mode Executor node).

    Args:
        plan_id: The plan ID.
        step_id: Step number (1-based).
        status: Step status (pending/running/completed/failed).
    """
    _send_plan_event({
        "type": "plan_updated",
        "plan_id": plan_id,
        "step_id": step_id,
        "status": status,
    })


def create_plan_create_tool():
    """Factory function to create the plan_create tool."""
    return plan_create


def create_plan_update_tool():
    """Factory function to create the plan_update tool."""
    return plan_update
