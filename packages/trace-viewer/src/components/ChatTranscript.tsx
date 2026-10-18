import { useEffect, useRef } from "react";
import type { ChatMessage } from "../types";
import { cx, formatTime } from "../utils";

export interface ChatTranscriptProps {
  messages: ChatMessage[];
  /** Messages after this ISO timestamp are dimmed (used to sync with replay position). */
  until?: string | null;
  /** Scroll to the newest visible message when messages change. */
  autoScroll?: boolean;
  className?: string;
}

const ROLE_LABEL: Record<ChatMessage["role"], string> = {
  user: "User",
  assistant: "Agent",
  info: "Info",
  infeasible: "Infeasible",
};

export function ChatTranscript({ messages, until, autoScroll = true, className }: ChatTranscriptProps) {
  const ref = useRef<HTMLOListElement>(null);
  const untilMs = until ? Date.parse(until) : null;
  const isFuture = (m: ChatMessage) => untilMs !== null && Date.parse(m.timestamp) > untilMs;
  const lastPastIndex = messages.reduce((acc, m, i) => (isFuture(m) ? acc : i), -1);

  useEffect(() => {
    if (!autoScroll || !ref.current) return;
    const el = ref.current.querySelector<HTMLElement>(`[data-msg-index="${lastPastIndex}"]`);
    el?.scrollIntoView?.({ block: "nearest" });
  }, [autoScroll, lastPastIndex, messages.length]);

  if (!messages.length) {
    return <div className={cx("stv-chat", "stv-empty", className)}>No messages</div>;
  }
  return (
    <ol className={cx("stv-chat", className)} ref={ref} aria-label="Chat transcript">
      {messages.map((m, i) => (
        <li
          key={i}
          data-msg-index={i}
          className={cx("stv-msg", `stv-msg--${m.role}`, isFuture(m) && "stv-msg--future")}
        >
          <div className="stv-msg__meta">
            <span className="stv-msg__role">{ROLE_LABEL[m.role]}</span>
            <time dateTime={m.timestamp}>{formatTime(m.timestamp)}</time>
          </div>
          <div className="stv-msg__body">{m.message}</div>
        </li>
      ))}
    </ol>
  );
}
