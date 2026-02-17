"""Plan Approval - Shared module for plan approval flow.

Extracted from app.py to avoid circular imports between app.py and agent.py.
Both modules import from here.
"""
import asyncio

# Global registry for pending plan approvals: plan_id -> asyncio.Event
_plan_approval_events: dict[str, asyncio.Event] = {}
_plan_approval_results: dict[str, bool] = {}


def register_plan_approval(plan_id: str) -> asyncio.Event:
    """Register a pending plan approval and return an Event to wait on."""
    evt = asyncio.Event()
    _plan_approval_events[plan_id] = evt
    return evt


def resolve_plan_approval(plan_id: str, approved: bool) -> bool:
    """Resolve a pending plan approval."""
    evt = _plan_approval_events.pop(plan_id, None)
    if evt is None:
        return False
    _plan_approval_results[plan_id] = approved
    evt.set()
    return True


def get_plan_approval_result(plan_id: str) -> bool:
    """Get the approval result for a plan."""
    return _plan_approval_results.pop(plan_id, True)
