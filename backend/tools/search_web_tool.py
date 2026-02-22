"""Search Web Tool - DuckDuckGo 搜索工具，用于获取互联网实时信息。"""
import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def search_web(query: str) -> str:
    """在互联网上搜索信息，返回相关结果摘要。

    使用 DuckDuckGo 搜索引擎查找最新资讯、技术文档、解决方案等。
    适用于需要实时信息或不确定具体 URL 的场景。

    Args:
        query: 搜索关键词或问题描述（字符串）

    Returns:
        搜索结果摘要（包含标题、链接和描述），或错误信息。

    Examples:
        - "Python asyncio 最佳实践"
        - "FastAPI streaming response 示例"
        - "LangChain agent 工具调用教程"
    """
    if not query or not query.strip():
        return "❌ 错误：搜索关键词不能为空"

    # 检查缓存（搜索结果相对稳定，可缓存）
    try:
        from cache import url_cache
        # 使用查询作为缓存键（添加前缀区分 URL 缓存）
        cache_key = f"search:{query.strip()}"
        cached = url_cache.get_cached_url(cache_key)
        if cached is not None:
            logger.info(f"✓ 搜索缓存命中: {query[:50]}")
            return "[CACHE_HIT]" + cached
    except Exception as e:
        logger.warning(f"缓存检查失败（将执行搜索）: {e}")

    try:
        # 导入 DuckDuckGo 搜索工具（使用新包名 ddgs）
        from ddgs import DDGS

        # 执行搜索（优化中文搜索）
        with DDGS() as ddgs:
            results = list(ddgs.text(
                query=query.strip(),     # 新 API 使用 query 参数
                safesearch='moderate',   # 适度安全搜索
                max_results=8,           # 限制结果数量避免 token 浪费
            ))

        if not results:
            return f"⚠️ 未找到相关结果：{query}"

        # 格式化搜索结果
        formatted_results = []
        for i, result in enumerate(results, 1):
            title = result.get("title", "无标题")
            link = result.get("href", "")
            snippet = result.get("body", "")

            formatted_results.append(
                f"{i}. **{title}**\n"
                f"   链接: {link}\n"
                f"   摘要: {snippet}\n"
            )

        output = (
            f"🔍 搜索关键词: {query}\n\n"
            + "\n".join(formatted_results)
        )

        # 限制输出长度
        if len(output) > 4000:
            output = output[:4000] + "\n\n...[结果已截断，仅显示前 4000 字符]"

        # 缓存搜索结果
        try:
            from cache import url_cache
            cache_key = f"search:{query.strip()}"
            url_cache.cache_url(cache_key, output)
        except Exception as e:
            logger.warning(f"缓存搜索结果失败: {e}")

        return output

    except ImportError:
        return (
            "❌ 错误：DuckDuckGo 搜索库未安装\n"
            "请运行: pip install ddgs"
        )
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return f"❌ 搜索失败: {str(e)}"


def create_search_web_tool():
    """工厂函数：创建网页搜索工具实例。"""
    return search_web
