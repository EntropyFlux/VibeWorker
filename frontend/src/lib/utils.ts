import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * 将 ISO 时间戳转换为相对时间描述。
 * - 不到 1 分钟 → "刚刚"
 * - 1-59 分钟 → "X分钟前"
 * - 1-23 小时 → "X小时前"
 * - 昨天 → "昨天"
 * - 今年内 → "MM-DD"
 * - 跨年 → "YY-MM-DD"
 */
export function formatRelativeTime(isoString: string): string {
  if (!isoString) return "";
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHour = Math.floor(diffMs / 3600000);

  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin}分钟前`;
  if (diffHour < 24) {
    // 检查是否跨天（如凌晨 1 点看昨晚 23 点的消息，diffHour < 24 但已经是昨天）
    const isYesterday = date.getDate() !== now.getDate();
    if (isYesterday) return "昨天";
    return `${diffHour}小时前`;
  }

  // 检查是否是昨天
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (
    date.getFullYear() === yesterday.getFullYear() &&
    date.getMonth() === yesterday.getMonth() &&
    date.getDate() === yesterday.getDate()
  ) {
    return "昨天";
  }

  // 同年显示 MM-DD，跨年显示 YY-MM-DD
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  if (date.getFullYear() === now.getFullYear()) {
    return `${mm}-${dd}`;
  }
  const yy = String(date.getFullYear()).slice(-2);
  return `${yy}-${mm}-${dd}`;
}
