/**
 * frontend/src/components/dashboard/ChatPanel.tsx
 *
 * Persistent conversational Q&A panel for the Chat tab.
 */

import React, { useState, useRef, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { sendChatMessage } from "../../api/chat";
import PlotlyChart from "./PlotlyChart";
import type { ChartSpec } from "../../types/chart";

interface LocalMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  chart?: ChartSpec | null;
  timestamp?: string;
}

interface ChatPanelProps {
  sessionId: string;
  initialMessages?: LocalMessage[];
  className?: string;
}

function AssistantAvatar(): React.ReactElement {
  return (
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--sage-accent)]">
      <svg className="h-3.5 w-3.5 text-white" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path d="M10 2a.75.75 0 01.692.462l1.41 3.393 3.664.293a.75.75 0 01.428 1.317l-2.79 2.39.85 3.575a.75.75 0 01-1.12.813L10 12.347l-3.134 1.896a.75.75 0 01-1.12-.813l.85-3.575-2.79-2.39a.75.75 0 01.428-1.317l3.665-.293 1.41-3.393A.75.75 0 0110 2z" />
      </svg>
    </div>
  );
}

function MessageBubble({ msg }: { msg: LocalMessage }): React.ReactElement {
  const isUser = msg.role === "user";
  return (
    <div className={["flex items-start gap-2.5", isUser ? "justify-end" : "justify-start"].join(" ")}>
      {!isUser && <AssistantAvatar />}
      <div className={["max-w-[80%] space-y-2", isUser ? "items-end" : "items-start"].join(" ")}>
        <div
          className={[
            "rounded-2xl px-4 py-3 text-sm leading-relaxed",
            isUser
              ? "rounded-tr-sm bg-[var(--sage-accent)] text-white"
              : "rounded-tl-sm bg-[var(--sage-bg-overlay)] text-[var(--sage-text-primary)]",
          ].join(" ")}
        >
          {msg.content}
        </div>
        {msg.chart && (
          <div className="w-full max-w-sm">
            <PlotlyChart chart={msg.chart} height={220} showExport={false} />
          </div>
        )}
      </div>
    </div>
  );
}

function TypingIndicator(): React.ReactElement {
  return (
    <div className="flex items-start justify-start gap-2.5">
      <AssistantAvatar />
      <div className="rounded-2xl rounded-tl-sm bg-[var(--sage-bg-overlay)] px-4 py-3">
        <div className="flex items-center gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--sage-text-dim)]"
              style={{ animationDelay: `${i * 120}ms` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function ChatPanel({
  sessionId,
  initialMessages = [],
  className = "",
}: ChatPanelProps): React.ReactElement {
  const [messages, setMessages] = useState<LocalMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const { mutate: send, isPending } = useMutation({
    mutationFn: ({ message }: { message: string }) =>
      sendChatMessage(sessionId, message),
    onMutate: ({ message }) => {
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "user", content: message },
      ]);
    },
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        {
          id: data.message.id,
          role: "assistant",
          content: data.message.content,
          chart: data.chart ?? null,
          timestamp: data.message.timestamp,
        },
      ]);
    },
    onError: () => {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "Sorry, I couldn't reach the server. Please try again.",
        },
      ]);
    },
  });

  function handleSubmit(e: React.FormEvent): void {
    e.preventDefault();
    const text = input.trim();
    if (!text || isPending) return;
    setInput("");
    send({ message: text });
  }

  return (
    <div
      className={[
        "mx-auto w-full max-w-4xl flex flex-col rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)]",
        className,
      ].join(" ")}
    >
      <div className="flex items-center gap-3 border-b border-[var(--sage-border)] px-5 py-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--sage-accent-soft)]">
          <svg className="h-4 w-4 text-[var(--sage-accent)]" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M18 10c0 3.866-3.582 7-8 7a8.84 8.84 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z" clipRule="evenodd" />
          </svg>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-[var(--sage-text-primary)]">Chat</h3>
          <p className="text-xs text-[var(--sage-text-muted)]">Ask anything about your dataset</p>
        </div>
      </div>
      <div className="flex-1 min-h-[560px] max-h-[70vh] space-y-3 overflow-y-auto p-5">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3 py-8 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-xl bg-[var(--sage-bg-overlay)]">
              <svg className="h-6 w-6 text-[var(--sage-text-dim)]" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M18 10c0 3.866-3.582 7-8 7a8.84 8.84 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z" clipRule="evenodd" />
              </svg>
            </div>
            <p className="text-base font-semibold text-[var(--sage-text-primary)]">Ask anything about your dataset</p>
            <p className="text-sm text-[var(--sage-text-dim)]">e.g. Which features drive the target? What columns have outliers?</p>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
        {isPending && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>
      <form
        onSubmit={handleSubmit}
        className="border-t border-[var(--sage-border)] p-3"
      >
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your data…"
            disabled={isPending}
            className={[
              "flex-1 rounded-xl border px-3.5 py-2 text-sm outline-none transition-colors",
              "border-[var(--sage-border-strong)] bg-[var(--sage-bg-base)] text-[var(--sage-text-primary)]",
              "placeholder:text-[var(--sage-text-dim)]",
              "focus:border-[var(--sage-accent-border)] focus:ring-2 focus:ring-[var(--sage-accent-soft)]",
              isPending ? "opacity-60" : "",
            ].join(" ")}
          />
          <button
            type="submit"
            disabled={isPending || !input.trim()}
            aria-label="Send message"
            className={[
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-colors",
              "bg-[var(--sage-accent)] text-white hover:opacity-90",
              "disabled:cursor-not-allowed disabled:opacity-40",
            ].join(" ")}
          >
            <svg className="h-4 w-4" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
              <path d="M2.25 8a.75.75 0 01.75-.75h8.19L8.47 4.56a.75.75 0 011.06-1.06l4 4a.75.75 0 010 1.06l-4 4a.75.75 0 11-1.06-1.06l2.72-2.69H3a.75.75 0 01-.75-.75z" />
            </svg>
          </button>
        </div>
      </form>
    </div>
  );
}
