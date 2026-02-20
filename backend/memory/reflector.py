"""反思记忆提取器 — 从工具失败中学习

当工具执行失败时，分析失败原因并提取可复用的经验，
存储为 procedural（程序性）记忆。

触发场景：
1. 工具返回错误
2. 工具返回空内容（如 fetch_url 对动态网页）
3. 重复尝试同类操作失败
4. 用户明确纠正 Agent 行为
"""
import logging
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


async def analyze_tool_failure(
    tool_name: str,
    tool_input: dict,
    error_message: str,
    user_feedback: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Optional[dict]:
    """分析工具失败并提取经验

    Args:
        tool_name: 工具名称
        tool_input: 工具输入参数
        error_message: 错误信息
        user_feedback: 用户反馈（可选）
        session_id: 会话 ID（用于追溯）

    Returns:
        如果提取出有价值的经验，返回 {content, salience, context}，否则 None
    """
    try:
        from engine.llm_factory import create_llm
        llm = create_llm()

        # 构建分析 prompt
        prompt = f"""你刚才执行工具时遇到了问题，请分析这次失败并提取可复用的经验。

工具信息：
- 工具名：{tool_name}
- 输入参数：{str(tool_input)[:500]}
- 错误信息：{error_message[:500]}
{"- 用户反馈：" + user_feedback[:300] if user_feedback else ""}

分析要求：
1. 判断这是否是一个值得记录的经验（而非偶发错误）
2. 如果值得记录，提取一条简洁、可复用的经验描述
3. 评估这条经验的重要性（0.7-1.0）

返回 JSON 格式：
- 如果值得记录：{{"content": "经验描述", "salience": 0.8, "error_type": "错误类型"}}
- 如果不值得记录：null

返回："""

        response = await llm.ainvoke(prompt)
        result = response.content.strip()

        # 解析响应
        import json
        try:
            # 清理可能的 markdown 标记
            if result.startswith("```"):
                lines = result.split("\n")
                result = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            if result.lower() == "null" or not result:
                return None

            data = json.loads(result)
            if not data or not isinstance(data, dict):
                return None

            content = data.get("content", "")
            if not content:
                return None

            return {
                "content": content,
                "salience": max(0.7, min(1.0, float(data.get("salience", 0.8)))),
                "context": {
                    "tool": tool_name,
                    "error_type": data.get("error_type", "unknown"),
                    "learned_from": session_id,
                },
            }

        except json.JSONDecodeError:
            logger.warning(f"无法解析反思结果: {result[:100]}")
            return None

    except Exception as e:
        logger.error(f"工具失败分析出错: {e}")
        return None


async def record_tool_failure(
    tool_name: str,
    tool_input: dict,
    error_message: str,
    user_feedback: Optional[str] = None,
    session_id: Optional[str] = None,
) -> bool:
    """记录工具失败并存储为程序性记忆

    Args:
        tool_name: 工具名称
        tool_input: 工具输入参数
        error_message: 错误信息
        user_feedback: 用户反馈（可选）
        session_id: 会话 ID

    Returns:
        是否成功记录
    """
    # 分析失败
    reflection = await analyze_tool_failure(
        tool_name=tool_name,
        tool_input=tool_input,
        error_message=error_message,
        user_feedback=user_feedback,
        session_id=session_id,
    )

    if not reflection:
        return False

    # 检查是否已有类似经验
    from memory.manager import memory_manager
    existing = memory_manager.get_procedural_memories(tool=tool_name)

    for e in existing:
        # 简单的相似度检查（可以用更复杂的方法）
        if _is_similar_experience(e.get("content", ""), reflection["content"]):
            logger.info(f"已存在类似的程序性记忆，跳过: {reflection['content'][:50]}...")
            return False

    # 存储为程序性记忆
    memory_manager.add_procedural_memory(
        content=reflection["content"],
        tool=tool_name,
        error_type=reflection["context"].get("error_type"),
        session_id=session_id,
        salience=reflection["salience"],
    )

    # 同时写入每日日志
    memory_manager.append_daily_log(
        content=f"{tool_name}: {reflection['content']}",
        log_type="reflection",
        tool=tool_name,
        error=error_message[:100],
    )

    logger.info(f"已记录程序性记忆: [{tool_name}] {reflection['content'][:50]}...")
    return True


def _is_similar_experience(existing: str, new: str) -> bool:
    """简单检查两条经验是否相似

    使用 Jaccard 相似度（与 MemoryManager.DUPLICATE_SIMILARITY_THRESHOLD 保持一致）。
    """
    from memory.manager import MemoryManager

    existing_words = set(existing.lower().split())
    new_words = set(new.lower().split())

    if not existing_words or not new_words:
        return False

    # 计算 Jaccard 相似度，使用统一阈值
    intersection = len(existing_words & new_words)
    union = len(existing_words | new_words)
    similarity = intersection / union if union > 0 else 0

    return similarity >= MemoryManager.DUPLICATE_SIMILARITY_THRESHOLD


def detect_user_correction(
    user_message: str,
    previous_assistant_message: Optional[str] = None,
) -> Optional[dict]:
    """检测用户对 Agent 行为的纠正

    识别模式：
    - "不要这样做..."
    - "下次不要..."
    - "这样做不对..."
    - "应该用...而不是..."

    Args:
        user_message: 用户消息
        previous_assistant_message: 前一条 assistant 消息

    Returns:
        如果检测到纠正，返回 {content, tool, salience}，否则 None
    """
    import re

    patterns = [
        # "不要" 模式
        r"(?:以后|下次)?不要(?:再)?(.+)",
        # "应该...而不是..." 模式
        r"应该(.+)而不是(.+)",
        # "这样做不对" 模式
        r"这样(?:做)?(?:不对|错了)[，,。]?\s*(.+)?",
        # "用...代替..." 模式
        r"用(.+)(?:代替|替代|取代)(.+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, user_message)
        if match:
            # 提取纠正内容
            groups = match.groups()
            content = " ".join(g for g in groups if g).strip()
            if content:
                return {
                    "content": f"用户纠正：{content}",
                    "tool": None,  # 可以从上下文推断
                    "salience": 0.9,  # 用户纠正通常很重要
                }

    return None


async def process_user_correction(
    user_message: str,
    previous_tool_call: Optional[dict] = None,
    session_id: Optional[str] = None,
) -> bool:
    """处理用户纠正并记录为程序性记忆

    Args:
        user_message: 用户消息
        previous_tool_call: 前一次工具调用信息
        session_id: 会话 ID

    Returns:
        是否成功记录
    """
    correction = detect_user_correction(user_message)
    if not correction:
        return False

    from memory.manager import memory_manager

    # 如果有前一次工具调用，关联工具名
    tool_name = None
    if previous_tool_call:
        tool_name = previous_tool_call.get("tool")

    if tool_name:
        memory_manager.add_procedural_memory(
            content=correction["content"],
            tool=tool_name,
            session_id=session_id,
            salience=correction["salience"],
        )
    else:
        # 作为一般性反思记录
        memory_manager.add_entry(
            content=correction["content"],
            category="reflections",
            salience=correction["salience"],
            source="user_correction",
        )

    logger.info(f"已记录用户纠正: {correction['content'][:50]}...")
    return True
