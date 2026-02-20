/**
 * 链接检测与转换工具
 *
 * 将文本中的裸 URL 和本地文件路径转换为可点击的 Markdown 链接，
 * 同时保留已有的 Markdown 链接格式不变。
 *
 * 支持的路径格式：
 * - Windows: C:\Users\xxx 或 C:/Users/xxx
 * - macOS/Linux: /Users/xxx 或 /home/xxx
 * - Home 目录: ~/Documents/xxx
 * - UNC: \\server\share
 */

/**
 * URL 正则表达式
 * 匹配 http/https/ftp 开头的链接
 * 注意：整个 URL 作为一个捕获组
 */
const URL_REGEX = /(?<![(\["a-zA-Z])(https?:\/\/[^\s<>\[\]"'`()\u4e00-\u9fa5]+)/gi;

/**
 * Windows 路径正则表达式
 * 匹配 C:\path 或 C:/path 格式，路径中可包含中文
 */
const WINDOWS_PATH_REGEX = /(?<![(\["])([A-Za-z]:[\\\/][^\s<>\[\]"'`*?|:]+\.[a-zA-Z0-9]+)/g;

/**
 * Unix/Mac 绝对路径正则表达式
 * 匹配 /Users/xxx 或 /home/xxx 格式（必须以常见根目录开头，避免误匹配）
 * 支持中文路径
 */
const UNIX_PATH_REGEX = /(?<![(\[":\/])(\/(?:Users|home|var|opt|etc|tmp|usr|mnt|media|Volumes)[^\s<>\[\]"'`*?|]+\.[a-zA-Z0-9]+)/g;

/**
 * Home 目录路径正则表达式
 * 匹配 ~/xxx 格式
 */
const HOME_PATH_REGEX = /(?<![(\["])(~\/[^\s<>\[\]"'`*?|]+\.[a-zA-Z0-9]+)/g;

/**
 * UNC 路径正则表达式
 * 匹配 \\server\share 格式
 */
const UNC_PATH_REGEX = /(?<![(\["])(\\\\[^\s<>\[\]"'`]+)/g;

/**
 * Markdown 链接正则表达式（用于检测已存在的链接）
 * 匹配 [text](url) 格式
 */
const MD_LINK_REGEX = /\[([^\]]*)\]\(([^)]+)\)/g;

/**
 * 检查位置是否在 Markdown 链接内部
 */
function isInsideMarkdownLink(text: string, start: number, end: number): boolean {
    MD_LINK_REGEX.lastIndex = 0;
    let match;
    while ((match = MD_LINK_REGEX.exec(text)) !== null) {
        const linkStart = match.index;
        const linkEnd = linkStart + match[0].length;
        if (start >= linkStart && end <= linkEnd) {
            return true;
        }
    }
    return false;
}

/**
 * 检查位置是否在代码块或行内代码内
 */
function isInsideCode(text: string, position: number): boolean {
    // 检查是否在 ``` 代码块内
    const codeBlockRegex = /```[\s\S]*?```/g;
    let match;
    while ((match = codeBlockRegex.exec(text)) !== null) {
        if (position >= match.index && position < match.index + match[0].length) {
            return true;
        }
    }

    // 检查是否在 ` 行内代码内
    const inlineCodeRegex = /`[^`]+`/g;
    while ((match = inlineCodeRegex.exec(text)) !== null) {
        if (position >= match.index && position < match.index + match[0].length) {
            return true;
        }
    }

    return false;
}

interface LinkMatch {
    start: number;
    end: number;
    text: string;
    type: 'url' | 'path';
}

/**
 * 检查两个区间是否重叠
 */
function isOverlapping(a: LinkMatch, b: LinkMatch): boolean {
    return !(a.end <= b.start || b.end <= a.start);
}

/**
 * 移除重叠的匹配，优先保留 URL 类型或更长的匹配
 */
function removeOverlaps(matches: LinkMatch[]): LinkMatch[] {
    if (matches.length <= 1) return matches;

    // 按起始位置排序
    const sorted = [...matches].sort((a, b) => a.start - b.start);
    const result: LinkMatch[] = [];

    for (const current of sorted) {
        // 检查是否与已有结果重叠
        let hasOverlap = false;
        for (let i = result.length - 1; i >= 0; i--) {
            if (isOverlapping(result[i], current)) {
                hasOverlap = true;
                // 如果当前是 URL 类型，或者比已有的更长，替换它
                if (current.type === 'url' || current.text.length > result[i].text.length) {
                    result[i] = current;
                }
                break;
            }
        }
        if (!hasOverlap) {
            result.push(current);
        }
    }

    return result;
}

/**
 * 查找所有需要转换的链接
 */
function findLinks(text: string): LinkMatch[] {
    const matches: LinkMatch[] = [];

    // 辅助函数：添加匹配
    const addMatches = (regex: RegExp, type: 'url' | 'path') => {
        regex.lastIndex = 0;
        let match;
        while ((match = regex.exec(text)) !== null) {
            const matchText = match[1] || match[0];
            const start = match.index + (match[0].indexOf(matchText));
            const end = start + matchText.length;

            if (!isInsideMarkdownLink(text, start, end) && !isInsideCode(text, start)) {
                matches.push({ start, end, text: matchText, type });
            }
        }
    };

    // 按优先级顺序添加匹配
    addMatches(URL_REGEX, 'url');
    addMatches(WINDOWS_PATH_REGEX, 'path');
    addMatches(UNIX_PATH_REGEX, 'path');
    addMatches(HOME_PATH_REGEX, 'path');
    addMatches(UNC_PATH_REGEX, 'path');

    // 移除重叠匹配
    const deduped = removeOverlaps(matches);

    // 按位置排序，从后往前处理以避免索引偏移
    deduped.sort((a, b) => b.start - a.start);

    return deduped;
}

/**
 * 将文本中的裸 URL 和本地路径转换为 Markdown 链接
 *
 * @param text 原始文本
 * @returns 转换后的文本
 */
export function linkifyText(text: string): string {
    const matches = findLinks(text);

    if (matches.length === 0) {
        return text;
    }

    let result = text;

    // 从后往前替换，避免索引偏移
    for (const match of matches) {
        const linkText = match.text;

        let href: string;
        if (match.type === 'url') {
            // URL 直接使用
            href = linkText;
        } else {
            // 本地路径转换为 file:// 协议
            // 将反斜杠转换为正斜杠
            const normalizedPath = linkText.replace(/\\/g, '/');
            // 处理 Windows 绝对路径：C:/... -> /C:/...
            if (/^[A-Za-z]:\//.test(normalizedPath)) {
                href = `file:///${normalizedPath}`;
            } else if (normalizedPath.startsWith('~')) {
                // ~ 路径：保持原样，前端无法展开
                href = `file://${normalizedPath}`;
            } else {
                // Unix 绝对路径
                href = `file://${normalizedPath}`;
            }
        }

        // 生成 Markdown 链接
        const markdownLink = `[${linkText}](${href})`;
        result = result.slice(0, match.start) + markdownLink + result.slice(match.end);
    }

    return result;
}

/**
 * 检查文本是否包含需要链接化的内容
 */
export function hasLinkifiableContent(text: string): boolean {
    return findLinks(text).length > 0;
}
