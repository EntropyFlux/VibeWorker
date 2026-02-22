"""流适配器 — 统一的 StateGraph 事件循环。

将 StateGraph astream_events 翻译为标准化的 AgentEvent dict。
同时从节点输出中提取 pending_events 侧通道事件。
"""
import logging
import time
from typing import AsyncGenerator, Optional, Union

from langgraph.types import Command

from engine import events

logger = logging.getLogger(__name__)


class ThinkTagFilter:
    """过滤推理模型（DeepSeek-R1、QwQ 等）输出中的 <think>...</think> 标签。

    流式传输中标签可能被拆分到多个 chunk（如 chunk1="<thi" chunk2="nk>"），
    因此使用缓冲区 + 状态机处理边界情况：
    - inside_think=False 时正常输出，遇到 <think> 进入抑制模式
    - inside_think=True 时丢弃内容，遇到 </think> 恢复输出
    - 缓冲区保留末尾可能的部分标签片段，等下一个 chunk 到达后再判断
    """

    OPEN_TAG = "<think>"
    CLOSE_TAG = "</think>"

    def __init__(self):
        self.inside_think = False
        self.buffer = ""
        self.reasoning = ""  # 累积的推理内容，供调试面板使用

    def feed(self, text: str) -> str:
        """输入一个 chunk，返回应输出的可见文本（think 内容被过滤但保留在 self.reasoning 中）。

        处理三种情况：
        1. 正常 <think>...</think> 成对出现
        2. <think> 和 </think> 跨越多个 chunk 或多次 LLM 调用
        3. 孤立的 </think>（某些 API 中转站剥离了开标签，或跨 LLM 调用时开标签在上一轮）
        """
        self.buffer += text
        output = ""

        while self.buffer:
            if self.inside_think:
                # 在 think 标签内，查找关闭标签
                close_pos = self.buffer.find(self.CLOSE_TAG)
                if close_pos != -1:
                    # 找到关闭标签 → 保存推理内容，恢复正常输出
                    self.reasoning += self.buffer[:close_pos]
                    self.buffer = self.buffer[close_pos + len(self.CLOSE_TAG):]
                    self.inside_think = False
                else:
                    # 未找到关闭标签 → 保留末尾可能是部分 </think> 的片段
                    partial = self._partial_end_match(self.buffer, self.CLOSE_TAG)
                    if partial:
                        # 安全部分存入 reasoning，可能的部分标签留在 buffer
                        self.reasoning += self.buffer[:-partial]
                        self.buffer = self.buffer[-partial:]
                    else:
                        self.reasoning += self.buffer
                        self.buffer = ""
                    break
            else:
                # 在 think 标签外，同时查找开始标签和孤立的关闭标签
                open_pos = self.buffer.find(self.OPEN_TAG)
                close_pos = self.buffer.find(self.CLOSE_TAG)

                # 确定最先出现的标签
                if open_pos != -1 and (close_pos == -1 or open_pos <= close_pos):
                    # 找到开始标签 → 输出标签前的内容，进入抑制模式
                    output += self.buffer[:open_pos]
                    self.buffer = self.buffer[open_pos + len(self.OPEN_TAG):]
                    self.inside_think = True
                elif close_pos != -1:
                    # 找到孤立的关闭标签（无匹配的开标签）→ 剥离标签，
                    # 标签前的内容视为推理残留（跨 LLM 调用的 think 块尾部）
                    self.reasoning += self.buffer[:close_pos]
                    self.buffer = self.buffer[close_pos + len(self.CLOSE_TAG):]
                else:
                    # 未找到任何标签 → 检查末尾是否有部分标签片段
                    partial = max(
                        self._partial_end_match(self.buffer, self.OPEN_TAG),
                        self._partial_end_match(self.buffer, self.CLOSE_TAG),
                    )
                    if partial:
                        output += self.buffer[:-partial]
                        self.buffer = self.buffer[-partial:]
                    else:
                        output += self.buffer
                        self.buffer = ""
                    break

        return output

    def flush(self) -> str:
        """流结束时刷新缓冲区，返回剩余可输出内容。"""
        if self.inside_think:
            # 仍在 think 内部，剩余内容属于推理过程
            self.reasoning += self.buffer
            self.buffer = ""
            return ""
        # 不在 think 内部，缓冲区中可能残留部分标签前缀（如 "<thi" 或 "</thi"）。
        # 这些前缀是为了等待下一个 chunk 判断是否构成完整标签而保留的。
        # 流结束时不会有更多 chunk 到来，直接检测并移除末尾的部分标签前缀。
        remaining = self.buffer
        self.buffer = ""
        # 先移除完整标签（理论上不应出现，但以防万一）
        for tag in (self.OPEN_TAG, self.CLOSE_TAG):
            remaining = remaining.replace(tag, "")
        # 再移除末尾的部分标签前缀
        for tag in (self.OPEN_TAG, self.CLOSE_TAG):
            stripped = self._strip_partial_tag_suffix(remaining, tag)
            if len(stripped) < len(remaining):
                remaining = stripped
                break  # 只可能有一个部分前缀在末尾
        return remaining

    @staticmethod
    def _strip_partial_tag_suffix(text: str, tag: str) -> str:
        """如果 text 末尾是 tag 的某个前缀（如 '<thi' 对 '<think>'），则去除它。"""
        for length in range(min(len(tag) - 1, len(text)), 0, -1):
            if text.endswith(tag[:length]):
                return text[:-length]
        return text

    def get_reasoning(self) -> str:
        """获取累积的推理内容（去除首尾空白）。"""
        return self.reasoning.strip()

    def extract_reasoning(self) -> str:
        """提取并清空已累积的推理内容，但保留 inside_think 状态和 buffer。

        用于在 llm_end 时获取本轮推理内容，同时保持过滤器状态跨 LLM 调用持续生效。
        这很重要，因为 <think> 块可能跨越多次 LLM 调用（中间穿插工具调用）。
        """
        result = self.reasoning.strip()
        self.reasoning = ""
        return result

    @staticmethod
    def _partial_end_match(text: str, tag: str) -> int:
        """检测 text 末尾与 tag 开头的重叠长度。

        例如 text="abc<thi", tag="<think>" → 返回 4（"<thi" 匹配 tag 前 4 字符）。
        用于处理标签被拆分到相邻 chunk 的边界情况。
        """
        max_check = min(len(tag) - 1, len(text))
        for length in range(max_check, 0, -1):
            if tag.startswith(text[-length:]):
                return length
        return 0


def _serialize_debug_messages(input_data) -> str:
    """序列化 LLM 输入消息，用于调试显示。

    直接显示传给 LLM 的消息列表（SystemMessage + HumanMessage + ...）。
    """
    messages = []

    if isinstance(input_data, dict):
        messages = input_data.get("messages", [])
    elif isinstance(input_data, list):
        messages = input_data

    # 处理嵌套列表：[[msg1, msg2, ...]]
    if messages and isinstance(messages[0], list):
        messages = messages[0]

    # 如果还是空的，尝试其他可能的键
    if not messages and isinstance(input_data, dict):
        for key in ["input", "content", "prompt"]:
            if key in input_data:
                val = input_data[key]
                if isinstance(val, list):
                    messages = val
                    break

    parts = []
    for msg in messages:
        # 获取消息类型
        role = type(msg).__name__
        # 获取消息内容
        if hasattr(msg, "content"):
            content = str(msg.content)
        elif isinstance(msg, dict):
            content = msg.get("content", str(msg))
            role = msg.get("role", msg.get("type", role))
        else:
            content = str(msg)
        parts.append(f"[{role}]\n{content}")

    return "\n---\n".join(parts) if parts else "(no messages)"


def _format_debug_input(messages_str: str) -> str:
    """格式化调试输入，直接返回消息字符串。"""
    return messages_str


# 节点到 motivation 的映射
_NODE_MOTIVATIONS = {
    "agent": "调用大模型进行推理",
    "executor_pre": "准备执行计划步骤",
    "executor": "执行计划步骤",
    "replanner": "评估是否需要调整计划",
    "summarizer": "生成计划执行总结",
}


async def stream_graph_events(
    graph,
    input_data: Union[dict, Command],
    config: dict,
    *,
    system_prompt: str = "",
) -> AsyncGenerator[dict, None]:
    """StateGraph astream_events → 标准化 AgentEvent dict 流。

    处理 5 类标准事件 + pending_events 侧通道：
    - on_chat_model_stream → TOKEN 事件
    - on_chat_model_start → LLM_START 事件
    - on_chat_model_end → LLM_END 事件
    - on_tool_start → TOOL_START 事件
    - on_tool_end → TOOL_END 事件
    - on_chain_end → 提取 pending_events（plan 侧通道事件）

    Args:
        graph: 编译后的 StateGraph
        input_data: 初始状态 dict 或 Command（resume 场景）
        config: 运行配置（含 thread_id 等）
        system_prompt: 用于调试输入格式化
    """
    from model_pool import resolve_model

    # 从 config 中获取 session_id
    sid = config.get("configurable", {}).get("session_id", "unknown")

    debug_tracking = {}
    seen_event_count = 0  # pending_events 消费计数器
    token_counts = {}  # 按节点统计 token 数量
    think_filter = ThinkTagFilter()  # 过滤推理模型的 <think> 标签

    async for event in graph.astream_events(input_data, version="v2", config=config):
        kind = event.get("event", "")
        metadata = event.get("metadata", {})

        if kind == "on_chat_model_stream":
            chunk = (event.get("data") or {}).get("chunk", None)
            if chunk and hasattr(chunk, "content") and chunk.content:
                node = metadata.get("langgraph_node", "unknown")
                token_counts[node] = token_counts.get(node, 0) + 1
                # chunk.content 可能是 str 或 list（DeepSeek-R1 等推理模型）
                raw = chunk.content
                if isinstance(raw, list):
                    # 列表格式：提取各部分的文本，reasoning_content 直接送入过滤器
                    parts = []
                    for item in raw:
                        if isinstance(item, dict):
                            parts.append(item.get("text", str(item)))
                        else:
                            parts.append(str(item))
                    content_str = "".join(parts)
                else:
                    content_str = str(raw)
                # 过滤推理模型的 <think>...</think> 标签
                filtered = think_filter.feed(content_str)
                if filtered:
                    yield events.build_token(filtered)

        elif kind == "on_chat_model_start":
            run_id = event.get("run_id", "")
            node = metadata.get("langgraph_node", "")
            data = event.get("data") or {}
            input_data_msg = data.get("input", {})
            input_messages = _serialize_debug_messages(input_data_msg)
            full_input = _format_debug_input(input_messages)
            debug_tracking[run_id] = {
                "start_time": time.time(),
                "node": node,
                "input": full_input,
            }

            mot = _NODE_MOTIVATIONS.get(node, "调用大模型处理请求")
            model_name = resolve_model("llm").get("model", "unknown")
            logger.info("[%s] Stream LLM 开始: node=%s, model=%s", sid, node, model_name)
            yield events.build_llm_start(run_id[:12], node, model_name, full_input, mot)

        elif kind == "on_chat_model_end":
            run_id = event.get("run_id", "")
            tracked = debug_tracking.pop(run_id, None)
            if tracked:
                node = tracked.get("node", "")
                dur = int((time.time() - tracked["start_time"]) * 1000)
                node_tokens = token_counts.get(node, 0)
                logger.info("[%s] Stream LLM 结束: node=%s, duration=%dms, stream_tokens=%d",
                            sid, node, dur, node_tokens)
                # 提取本轮 LLM 调用累积的推理内容，附加到 llm_end 事件。
                # 注意：使用 extract_reasoning() 而非重置过滤器，
                # 因为 <think> 块可能跨越多次 LLM 调用（中间穿插工具调用）。
                reasoning = think_filter.extract_reasoning()
                llm_end_event = events.build_llm_end_from_raw(event, tracked)
                if reasoning:
                    llm_end_event["reasoning"] = reasoning
                yield llm_end_event

        elif kind == "on_tool_start":
            run_id = event.get("run_id", "")
            tool_name = event.get("name", "unknown")
            debug_tracking[f"tool_{run_id}"] = {"start_time": time.time(), "name": tool_name}
            logger.info("[%s] Stream 工具开始: %s", sid, tool_name)
            yield events.build_tool_start_from_raw(event)

        elif kind == "on_tool_end":
            run_id = event.get("run_id", "")
            tracked = debug_tracking.pop(f"tool_{run_id}", None)
            duration_ms = int((time.time() - tracked["start_time"]) * 1000) if tracked else None
            tool_name = tracked.get("name", "unknown") if tracked else "unknown"
            logger.info("[%s] Stream 工具结束: %s, duration=%dms", sid, tool_name, duration_ms or 0)
            yield events.build_tool_end_from_raw(event, duration_ms)

        elif kind == "on_chain_end":
            # 从节点输出中提取 pending_events
            output = (event.get("data") or {}).get("output", {})
            if isinstance(output, dict):
                pending = output.get("pending_events", [])
                if isinstance(pending, list):
                    # 只 yield 新增的事件
                    new_events = pending[seen_event_count:]
                    for pe in new_events:
                        if isinstance(pe, dict) and "type" in pe:
                            yield pe
                    seen_event_count = len(pending)

    # 流结束，刷新 think 标签过滤器缓冲区（输出可能残留的非 think 内容）
    remaining = think_filter.flush()
    if remaining:
        yield events.build_token(remaining)

    # 流结束，输出各节点 token 统计
    if token_counts:
        logger.info("[%s] Stream 结束, 各节点 token 统计: %s", sid, token_counts)
