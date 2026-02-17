"""Agent Graph - Hybrid Agent architecture with LangGraph runtime.

Unified entry: ReAct agent (Phase 1) handles all requests.
When the agent calls plan_create, the system auto-triggers Phase 2
(Plan Execution Loop) with isolated executor sub-agents and replanner.
"""
import json
import logging
import time
from typing import Optional, Callable
from uuid import uuid4

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from config import settings
from prompt_builder import build_system_prompt
from tools import get_all_tools, get_executor_tools

logger = logging.getLogger(__name__)

# SSE callback for security approval requests
_sse_approval_callback: Optional[Callable] = None


def set_sse_approval_callback(callback: Optional[Callable]) -> None:
    """Set the SSE callback used by SecurityGate for approval requests."""
    global _sse_approval_callback
    _sse_approval_callback = callback
    try:
        from security import security_gate
        security_gate.set_sse_callback(callback)
    except Exception:
        pass


def create_llm(streaming: bool = True) -> ChatOpenAI:
    """Create and configure the LLM instance using model pool."""
    from model_pool import resolve_model
    cfg = resolve_model("llm")
    return ChatOpenAI(
        model=cfg["model"],
        api_key=cfg["api_key"],
        base_url=cfg["api_base"],
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        streaming=streaming,
    )


def create_agent_graph():
    """Create the ReAct Agent using LangGraph's create_react_agent.

    This is the unified entry point (Phase 1) with all tools including
    plan_create. When plan_create is called, Phase 2 is triggered automatically.
    """
    llm = create_llm()
    tools = get_all_tools()
    system_prompt = build_system_prompt()

    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=system_prompt,
    )

    return agent


# ============================================
# Replanner structured output
# ============================================

class ReplanDecision(BaseModel):
    """Decision from the Replanner LLM."""
    action: str = Field(description="决策动作: continue(继续执行下一步) / revise(修改后续计划) / finish(任务完成，生成最终回复)")
    response: str = Field(default="", description="当 action=finish 时的最终回复内容")
    revised_steps: list[str] = Field(default_factory=list, description="当 action=revise 时的新步骤列表")
    reason: str = Field(default="", description="决策原因说明")


# ============================================
# Debug helpers
# ============================================

def _serialize_debug_messages(input_data) -> str:
    """Serialize LLM input messages for debug display."""
    messages = input_data.get("messages", [])
    if messages and isinstance(messages[0], list):
        messages = messages[0]
    parts = []
    for msg in messages:
        role = type(msg).__name__
        content = str(msg.content) if hasattr(msg, "content") else str(msg)
        parts.append(f"[{role}]\n{content}")
    return "\n---\n".join(parts)


def _format_debug_input(system_prompt: str, messages_str: str, instruction: str = None) -> str:
    """Format input for debug display with consistent structure."""
    parts = [f"[System Prompt]\n{system_prompt}"]
    if instruction:
        parts.append(f"[Instruction]\n{instruction}")
    parts.append(f"[Messages]\n{messages_str}")
    return "\n\n".join(parts)


# ============================================
# Main entry point
# ============================================

async def run_agent(
    message: str,
    session_history: list[dict],
    stream: bool = True,
    debug: bool = False,
):
    """Run the agent with a user message.

    Yields event dicts with type and content for SSE streaming.
    """
    if not settings.enable_llm_cache:
        async for event in _run_agent_no_cache(message, session_history, stream, debug):
            yield event
        return

    # LLM cache enabled
    system_prompt = build_system_prompt()
    recent_history = []
    for msg in session_history[-3:]:
        recent_history.append({
            "role": msg.get("role", ""),
            "content": msg.get("content", "")[:500],
        })

    cache_key_params = {
        "system_prompt": system_prompt,
        "recent_history": recent_history,
        "current_message": message,
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
    }

    from cache import llm_cache

    async def generator():
        async for event in _run_agent_no_cache(message, session_history, stream, debug):
            yield event

    async for event in llm_cache.get_or_generate(
        key_params=cache_key_params,
        generator_func=generator,
        stream=stream,
    ):
        yield event


async def _run_agent_no_cache(
    message: str,
    session_history: list[dict],
    stream: bool = True,
    debug: bool = False,
):
    """Run the agent without caching.

    Always uses the unified ReAct agent (Phase 1).
    Phase 2 is triggered automatically when plan_create is called.
    """
    async for event in _stream_simple_agent(message, session_history, stream, debug):
        yield event


# ============================================
# Phase 1: ReAct Agent (unified entry)
# ============================================

async def _stream_simple_agent(
    message: str,
    session_history: list[dict],
    stream: bool = True,
    debug: bool = False,
):
    """Phase 1: ReAct agent as unified entry point.

    When plan_create tool is detected, breaks out and enters Phase 2.
    """
    system_prompt = build_system_prompt()
    agent = create_agent_graph()

    messages = []
    for msg in session_history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=message))

    input_state = {"messages": messages}
    config = {"recursion_limit": settings.agent_recursion_limit}

    if stream:
        debug_tracking = {}
        plan_detected = False
        plan_data = None

        async for event in agent.astream_events(input_state, version="v2", config=config):
            kind = event.get("event", "")
            metadata = event.get("metadata", {})

            if kind == "on_chat_model_stream":
                chunk = (event.get("data") or {}).get("chunk", None)
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield {
                        "type": "token",
                        "content": chunk.content,
                    }

            elif kind == "on_chat_model_start":
                run_id = event.get("run_id", "")
                node = metadata.get("langgraph_node", "")
                input_data = (event.get("data") or {}).get("input", {})
                input_messages = _serialize_debug_messages(input_data)
                full_input = _format_debug_input(system_prompt, input_messages)
                debug_tracking[run_id] = {
                    "start_time": time.time(),
                    "node": node,
                    "input": full_input,
                }

                motivation_map = {
                    "agent": "调用大模型进行推理",
                }
                motivation = motivation_map.get(node, "调用大模型处理请求")

                from model_pool import resolve_model
                model_name = resolve_model("llm").get("model", "unknown")
                yield {
                    "type": "llm_start",
                    "call_id": run_id[:12],
                    "node": node,
                    "model": model_name,
                    "input": full_input[:5000],
                    "motivation": motivation,
                }

            elif kind == "on_chat_model_end":
                run_id = event.get("run_id", "")
                tracked = debug_tracking.pop(run_id, None)
                if tracked:
                    yield _build_llm_end_event(event, tracked)

            elif kind == "on_tool_start":
                if debug:
                    run_id = event.get("run_id", "")
                    debug_tracking[f"tool_{run_id}"] = {"start_time": time.time()}

                yield _build_tool_start_event(event)

            elif kind == "on_tool_end":
                tool_name = event.get("name", "")
                duration_ms = None
                if debug:
                    run_id = event.get("run_id", "")
                    tracked = debug_tracking.pop(f"tool_{run_id}", None)
                    if tracked:
                        duration_ms = int((time.time() - tracked["start_time"]) * 1000)

                yield _build_tool_end_event(event, duration_ms)

                # Phase 2 trigger: detect plan_create tool completion
                if tool_name == "plan_create":
                    from tools.plan_tool import get_latest_plan
                    plan_data = get_latest_plan()
                    if plan_data:
                        plan_detected = True
                        break

        if plan_detected and plan_data:
            # Phase 2: Plan Execution
            plan_id = plan_data["plan_id"]

            # Approval gate (optional)
            if settings.plan_require_approval:
                from plan_approval import register_plan_approval, get_plan_approval_result
                from tools.plan_tool import _send_plan_event

                _send_plan_event({
                    "type": "plan_approval_request",
                    "plan_id": plan_id,
                    "title": plan_data["title"],
                    "steps": plan_data["steps"],
                })

                approval_event = register_plan_approval(plan_id)
                await approval_event.wait()
                approved = get_plan_approval_result(plan_id)

                if not approved:
                    yield {"type": "token", "content": "\n\n用户已拒绝计划执行。"}
                    yield {"type": "done"}
                    return

            # Enter Phase 2 execution loop
            async for event in _stream_plan_execution(
                plan_data, messages, system_prompt, debug
            ):
                yield event
        else:
            yield {"type": "done"}

    else:
        # Non-streaming mode
        result = await agent.ainvoke(input_state, config=config)
        final_messages = result.get("messages", [])
        if final_messages:
            last_msg = final_messages[-1]
            yield {
                "type": "message",
                "content": last_msg.content if hasattr(last_msg, "content") else str(last_msg),
            }
        yield {"type": "done"}


# ============================================
# Phase 2: Plan Execution Loop
# ============================================

async def _stream_plan_execution(
    plan_data: dict,
    original_messages: list,
    system_prompt: str,
    debug: bool = False,
):
    """Phase 2: Execute plan steps with isolated executor sub-agents.

    Each step gets its own sub-agent with executor tools.
    After each step, the replanner evaluates whether to continue, revise, or finish.
    """
    from tools.plan_tool import send_plan_updated_event, send_plan_revised_event
    from model_pool import resolve_model

    plan_id = plan_data["plan_id"]
    plan_title = plan_data["title"]
    steps = plan_data["steps"]  # list of {"id": int, "title": str, "status": str}
    model_name = resolve_model("llm").get("model", "unknown")

    past_steps: list[tuple[str, str]] = []
    step_index = 0

    while step_index < len(steps) and step_index < settings.plan_max_steps:
        step = steps[step_index]
        step_title = step["title"] if isinstance(step, dict) else str(step)
        step_id = step["id"] if isinstance(step, dict) else step_index + 1

        # Mark step as running
        send_plan_updated_event(plan_id, step_id, "running")

        # Build context from past steps
        past_context = ""
        if past_steps:
            past_context = "\n".join(
                f"步骤 {i+1} [{s}]: {r[:300]}" for i, (s, r) in enumerate(past_steps)
            )

        executor_prompt = f"""{system_prompt}

计划标题：{plan_title}
当前步骤（{step_index + 1}/{len(steps)}）：{step_title}

{f'已完成的步骤：{chr(10)}{past_context}' if past_context else ''}

请专注完成当前步骤。完成后简要总结结果。"""

        executor_llm = create_llm(streaming=True)
        executor_tools = get_executor_tools()
        sub_agent = create_react_agent(
            model=executor_llm,
            tools=executor_tools,
            prompt=executor_prompt,
        )

        input_messages = list(original_messages)
        input_messages.append(HumanMessage(content=f"执行步骤 {step_index + 1}: {step_title}"))

        sub_config = {"recursion_limit": 30}
        debug_tracking = {}
        step_response = ""

        async for event in sub_agent.astream_events(
            {"messages": input_messages}, version="v2", config=sub_config,
        ):
            kind = event.get("event", "")
            evt_metadata = event.get("metadata", {})

            if kind == "on_chat_model_stream":
                chunk = (event.get("data") or {}).get("chunk", None)
                if chunk and hasattr(chunk, "content") and chunk.content:
                    step_response += chunk.content
                    yield {"type": "token", "content": chunk.content}

            elif kind == "on_chat_model_start":
                run_id = event.get("run_id", "")
                node = evt_metadata.get("langgraph_node", "")
                input_data = (event.get("data") or {}).get("input", {})
                input_msgs_str = _serialize_debug_messages(input_data)
                full_input = _format_debug_input(system_prompt, input_msgs_str, executor_prompt)
                debug_tracking[run_id] = {
                    "start_time": time.time(),
                    "node": "executor",
                    "input": full_input,
                }
                yield {
                    "type": "llm_start",
                    "call_id": run_id[:12],
                    "node": "executor",
                    "model": model_name,
                    "input": full_input[:5000],
                    "motivation": f"执行步骤 {step_index + 1}: {step_title}",
                }

            elif kind == "on_chat_model_end":
                run_id = event.get("run_id", "")
                tracked = debug_tracking.pop(run_id, None)
                if tracked:
                    yield _build_llm_end_event(event, tracked)

            elif kind == "on_tool_start":
                if debug:
                    run_id = event.get("run_id", "")
                    debug_tracking[f"tool_{run_id}"] = {"start_time": time.time()}
                yield _build_tool_start_event(event)

            elif kind == "on_tool_end":
                duration_ms = None
                if debug:
                    run_id = event.get("run_id", "")
                    tracked = debug_tracking.pop(f"tool_{run_id}", None)
                    if tracked:
                        duration_ms = int((time.time() - tracked["start_time"]) * 1000)
                yield _build_tool_end_event(event, duration_ms)

        # Mark step completed
        send_plan_updated_event(plan_id, step_id, "completed")
        past_steps.append((step_title, step_response[:1000]))
        step_index += 1

        # Replanner evaluation
        remaining = len(steps) - step_index
        if remaining > 0:
            decision = await _evaluate_replan(
                plan_title, steps, past_steps, step_index, system_prompt
            )

            if decision:
                if decision.action == "finish":
                    # Mark remaining steps as skipped (completed)
                    for i in range(step_index, len(steps)):
                        s = steps[i]
                        sid = s["id"] if isinstance(s, dict) else i + 1
                        send_plan_updated_event(plan_id, sid, "completed")

                    if decision.response:
                        yield {"type": "token", "content": "\n\n" + decision.response}
                    break

                elif decision.action == "revise" and decision.revised_steps:
                    # Build new steps from revision
                    new_steps = [
                        {"id": step_index + i + 1, "title": s.strip(), "status": "pending"}
                        for i, s in enumerate(decision.revised_steps)
                    ]
                    send_plan_revised_event(
                        plan_id, new_steps, step_index, decision.reason
                    )
                    # Replace remaining steps
                    steps = steps[:step_index] + new_steps

    yield {"type": "done"}


# ============================================
# Replanner
# ============================================

async def _evaluate_replan(
    plan_title: str,
    steps: list,
    past_steps: list[tuple[str, str]],
    current_index: int,
    system_prompt: str,
) -> Optional[ReplanDecision]:
    """Evaluate whether to continue, revise, or finish the plan.

    Returns None if replanning is disabled or evaluation fails (degrades to continue).
    """
    if not settings.plan_revision_enabled:
        return None

    remaining_steps = steps[current_index:]
    if not remaining_steps:
        return None

    past_str = "\n".join(
        f"步骤 {i+1} [{s}]: {r[:200]}" for i, (s, r) in enumerate(past_steps)
    )
    remaining_str = "\n".join(
        f"步骤 {(s['id'] if isinstance(s, dict) else current_index + i + 1)}: "
        f"{(s['title'] if isinstance(s, dict) else str(s))}"
        for i, s in enumerate(remaining_steps)
    )

    replan_prompt = f"""你是一个计划评估专家。请根据当前执行进度评估是否需要调整计划。

计划标题：{plan_title}

已完成的步骤：
{past_str}

剩余步骤：
{remaining_str}

请选择一个动作：
- **continue**: 剩余步骤合理，继续执行下一步
- **revise**: 根据已完成步骤的结果，需要修改剩余步骤
- **finish**: 任务目标已经达成，无需继续执行剩余步骤

请以 JSON 格式回复。"""

    try:
        llm = create_llm(streaming=False)
        structured_llm = llm.with_structured_output(ReplanDecision)
        decision = await structured_llm.ainvoke(replan_prompt)
        logger.info(f"[REPLANNER] decision: {decision.action} - {decision.reason}")
        return decision
    except Exception as e:
        logger.warning(f"[REPLANNER] evaluation failed, degrading to continue: {e}")
        return None


# ============================================
# Shared event builder helpers
# ============================================

def _build_llm_end_event(event: dict, tracked: dict) -> dict:
    """Build an llm_end SSE event from astream_events data."""
    run_id = event.get("run_id", "")
    output_msg = (event.get("data") or {}).get("output", None)
    duration_ms = int((time.time() - tracked["start_time"]) * 1000)

    tokens = {}
    if output_msg and hasattr(output_msg, "usage_metadata") and output_msg.usage_metadata:
        um = output_msg.usage_metadata
        tokens = {
            "input_tokens": getattr(um, "input_tokens", None) or (um.get("input_tokens") if isinstance(um, dict) else None),
            "output_tokens": getattr(um, "output_tokens", None) or (um.get("output_tokens") if isinstance(um, dict) else None),
            "total_tokens": getattr(um, "total_tokens", None) or (um.get("total_tokens") if isinstance(um, dict) else None),
        }

    output_parts = []
    if output_msg:
        if hasattr(output_msg, "content"):
            content = output_msg.content
            if isinstance(content, list):
                content_str = " ".join(
                    item.get("text", str(item)) if isinstance(item, dict) else str(item)
                    for item in content
                )
            else:
                content_str = str(content) if content else ""
            if content_str.strip():
                output_parts.append(content_str)

        tool_calls = []
        if hasattr(output_msg, "tool_calls") and output_msg.tool_calls:
            for tc in output_msg.tool_calls:
                tc_info = {
                    "name": getattr(tc, "name", getattr(tc, "function", {}).get("name") if hasattr(tc, "function") else "unknown"),
                    "arguments": getattr(tc, "arguments", getattr(tc, "function", {}).get("arguments") if hasattr(tc, "function") else ""),
                }
                tool_calls.append(tc_info)

        if tool_calls:
            output_parts.append("[TOOL_CALLS]: " + json.dumps(tool_calls, ensure_ascii=False, indent=2))

        if not output_parts and hasattr(output_msg, "additional_kwargs") and output_msg.additional_kwargs:
            output_parts.append(str(output_msg.additional_kwargs))

        if not output_parts:
            output_parts.append(str(output_msg))

    output_text = "\n\n".join(output_parts) if output_parts else "(no content)"

    from model_pool import resolve_model
    model_name = resolve_model("llm").get("model", "unknown")

    return {
        "type": "llm_end",
        "call_id": run_id[:12],
        "node": tracked["node"],
        "model": model_name,
        "duration_ms": duration_ms,
        "input_tokens": tokens.get("input_tokens"),
        "output_tokens": tokens.get("output_tokens"),
        "total_tokens": tokens.get("total_tokens"),
        "input": tracked["input"][:5000],
        "output": output_text[:3000],
    }


def _build_tool_start_event(event: dict) -> dict:
    """Build a tool_start SSE event."""
    tool_name = event.get("name", "")
    tool_input = (event.get("data") or {}).get("input", {})

    tool_motivation_map = {
        "read_file": "读取文件内容",
        "write_file": "写入文件",
        "terminal": "执行终端命令",
        "python_repl": "执行 Python 代码",
        "search_knowledge_base": "搜索知识库",
        "memory_search": "搜索记忆",
        "memory_write": "写入记忆",
        "fetch_url": "获取网页内容",
        "plan_create": "创建任务计划",
        "plan_update": "更新任务计划",
    }
    motivation = tool_motivation_map.get(tool_name, f"调用工具：{tool_name}")

    return {
        "type": "tool_start",
        "tool": tool_name,
        "input": str(tool_input),
        "motivation": motivation,
    }


def _build_tool_end_event(event: dict, duration_ms: Optional[int] = None) -> dict:
    """Build a tool_end SSE event."""
    tool_name = event.get("name", "")
    tool_output = (event.get("data") or {}).get("output", "")

    if hasattr(tool_output, 'content'):
        output_str = str(tool_output.content)
    else:
        output_str = str(tool_output)

    output_str = output_str[:2000]

    is_cached = output_str.startswith('[CACHE_HIT]')
    if is_cached:
        logger.info(f"✓ Cache hit for tool: {tool_name}")

    return {
        "type": "tool_end",
        "tool": tool_name,
        "output": output_str,
        "cached": is_cached,
        "duration_ms": duration_ms,
    }
