"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Bot, Info, Loader2, Send, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { ChatMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

const ROLE_ICON = { user: User, assistant: Bot, info: Info, infeasible: AlertTriangle } as const;

export function ChatPanel({
  messages,
  onSend,
  disabled,
  className,
}: {
  messages: ChatMessage[];
  onSend: (message: string) => Promise<void>;
  disabled?: boolean;
  className?: string;
}) {
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages.length]);

  async function send(e?: React.FormEvent) {
    e?.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);
    setError(null);
    try {
      await onSend(text);
      setDraft("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3" data-testid="chat-messages">
        {messages.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">No messages yet.</p>}
        {messages.map((m, i) => {
          const Icon = ROLE_ICON[m.role];
          if (m.role === "info" || m.role === "infeasible") {
            return (
              <div
                key={i}
                className={cn(
                  "flex items-start gap-2 rounded-lg px-3 py-2 text-xs",
                  m.role === "infeasible" ? "bg-amber-500/10 text-amber-800 dark:text-amber-200" : "bg-muted text-muted-foreground",
                )}
              >
                <Icon className="mt-0.5 size-3.5 shrink-0" />
                <span className="break-words">{m.message}</span>
              </div>
            );
          }
          const mine = m.role === "user";
          return (
            <div key={i} className={cn("flex items-end gap-2", mine && "flex-row-reverse")}>
              <span className={cn("grid size-6 shrink-0 place-items-center rounded-full", mine ? "bg-primary text-primary-foreground" : "bg-muted")}>
                <Icon className="size-3.5" />
              </span>
              <div
                className={cn(
                  "max-w-[80%] rounded-2xl px-3 py-2 text-sm break-words",
                  mine ? "rounded-br-sm bg-primary text-primary-foreground" : "rounded-bl-sm bg-muted",
                )}
              >
                {m.message}
                <time className={cn("mt-0.5 block text-[10px] opacity-60", mine && "text-right")} dateTime={m.timestamp}>
                  {new Date(m.timestamp).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </time>
              </div>
            </div>
          );
        })}
        <div ref={endRef} />
      </div>
      <form onSubmit={send} className="border-t p-3">
        {error && <p className="mb-2 text-xs text-destructive">{error}</p>}
        <div className="flex items-end gap-2">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder={disabled ? "Run finished — messages are still recorded" : "Message the agent…"}
            rows={1}
            className="max-h-32 min-h-9 resize-none"
            aria-label="Chat message"
          />
          <Button type="submit" size="icon" disabled={!draft.trim() || sending} aria-label="Send message">
            {sending ? <Loader2 className="animate-spin" /> : <Send />}
          </Button>
        </div>
      </form>
    </div>
  );
}
