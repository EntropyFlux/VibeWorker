"use client";

import { useState, useEffect, useRef, useCallback } from "react";

interface TypewriterProps {
  /** 目标文本（可能持续增长） */
  text: string;
  /** 基础速度（毫秒/字符），默认 20ms，积压少时使用此速度 */
  speed?: number;
  /** 是否正在流式输入中（用于判断是否继续动画） */
  isStreaming?: boolean;
  /** 渲染函数，接收当前应显示的文本 */
  children: (displayText: string) => React.ReactNode;
}

/**
 * 自适应速度打字机组件
 *
 * 根据待显示字符的积压量（buffer = 目标长度 - 已显示位置）动态调整输出速度，
 * 同时调节 tick 间隔和每 tick 输出字符数，实现"双管齐下"的加速策略：
 *
 * - 积压 ≤ 3：保持自然打字节奏（1字符/tick，基础速度）
 * - 积压 4~15：轻微加速（1字符/tick，间隔缩短 40%）
 * - 积压 16~50：中等加速（2字符/tick，间隔缩短到 5ms）
 * - 积压 51~150：明显加速（按比例多字符/tick，间隔 4ms）
 * - 积压 > 150：快速追赶，跳过大段只保留少量 buffer 维持动画感
 *
 * 使用递归 setTimeout 替代 setInterval，每次 tick 根据最新积压量重新计算参数，
 * 确保速度实时响应后台数据到达速率的变化。
 */
export function Typewriter({
  text,
  speed = 20,
  isStreaming = true,
  children,
}: TypewriterProps) {
  // 当前显示到的字符索引（React 状态，驱动渲染）
  const [displayIndex, setDisplayIndex] = useState(0);
  // 用 ref 追踪最新值，避免递归 setTimeout 中的闭包陈旧问题
  const displayIndexRef = useRef(0);
  const textRef = useRef(text);
  const speedRef = useRef(speed);
  // 定时器引用（setTimeout，非 setInterval）
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 同步 ref 到最新的 props
  textRef.current = text;
  speedRef.current = speed;

  /**
   * 根据积压量计算本次 tick 的输出参数
   * 返回：charsPerTick（本次输出字符数）、delay（距下次 tick 的延迟 ms）
   */
  const computeTickParams = useCallback(
    (buffer: number): { charsPerTick: number; delay: number } => {
      const baseSpeed = speedRef.current;

      if (buffer <= 3) {
        // 积压极少：原始打字感，1 字符 / 基础速度
        return { charsPerTick: 1, delay: baseSpeed };
      }
      if (buffer <= 15) {
        // 轻微积压：略微加快 interval，仍然单字符输出
        return { charsPerTick: 1, delay: Math.max(baseSpeed * 0.6, 8) };
      }
      if (buffer <= 50) {
        // 中等积压：每次 2 字符 + 缩短间隔
        return { charsPerTick: 2, delay: Math.max(baseSpeed * 0.3, 5) };
      }
      if (buffer <= 150) {
        // 较大积压：按比例输出更多字符，间隔压到 4ms
        return { charsPerTick: Math.ceil(buffer / 15), delay: 4 };
      }
      // 极大积压（>150）：大幅跳跃，保留 ~30 字符的 buffer 维持尾部动画感
      return { charsPerTick: buffer - 30, delay: 3 };
    },
    [] // speedRef 是 ref，不需要作为依赖
  );

  /**
   * 递归调度下一次 tick
   * 每次 tick 读取最新的 ref 值，计算积压量并决定输出参数
   */
  const scheduleNextTick = useCallback(() => {
    const currentIndex = displayIndexRef.current;
    const targetLength = textRef.current.length;
    const buffer = targetLength - currentIndex;

    // 已追上目标文本，停止调度
    if (buffer <= 0) {
      timerRef.current = null;
      return;
    }

    const { charsPerTick, delay } = computeTickParams(buffer);

    timerRef.current = setTimeout(() => {
      // 计算新的显示位置，确保不超过目标长度
      const newIndex = Math.min(
        displayIndexRef.current + charsPerTick,
        textRef.current.length
      );
      displayIndexRef.current = newIndex;
      setDisplayIndex(newIndex);

      // 递归调度，下一次 tick 会重新计算积压量
      scheduleNextTick();
    }, delay);
  }, [computeTickParams]);

  // 当文本长度增长时，如果定时器未在运行则启动追赶
  useEffect(() => {
    if (displayIndexRef.current < text.length && !timerRef.current) {
      scheduleNextTick();
    }
  }, [text.length, scheduleNextTick]);

  // 流式结束时立即显示全部剩余内容
  useEffect(() => {
    if (!isStreaming && displayIndexRef.current < text.length) {
      // 先清除正在进行的定时器
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      displayIndexRef.current = text.length;
      setDisplayIndex(text.length);
    }
  }, [isStreaming, text.length]);

  // 组件卸载时清理定时器
  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  // 计算当前应显示的文本
  const displayText = text.slice(0, displayIndex);

  return <>{children(displayText)}</>;
}

export default Typewriter;
