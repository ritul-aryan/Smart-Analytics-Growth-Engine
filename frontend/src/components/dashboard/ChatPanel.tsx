/**
 * frontend/src/components/dashboard/ChatPanel.tsx
 *
 * Persistent conversational Q&A panel for the Chat tab.
 *
 * Loads full history from the session's chat_messages on mount (via
 * GET /api/session/{id} which includes chat history).  Sends new messages
 * via POST /api/chat.  If the assistant response includes a chart spec it
 * is rendered inline using PlotlyChart.
 *
 * History persists across page refresh because all messages are stored
 * in the chat_messages DB table — this fixes prototype Limitation L17.
 *
 * Usage:
 *   <ChatPanel sessionId={session.id} initialMessages={chatMessages} />
 */

import React, { useState, useRef, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { sendChatMessage } from "../../api/chat";
import PlotlyChart from "./PlotlyChart";
import type { ChartSpec } from "../../types/chart";

// ---------------------------------------------------------------------------
// Local message type (union of DB history + optimistic local messages)
// ---------------------------------------------------------------------------

interface LocalMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  chart?: ChartSpec | null;
  timestamp?: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ChatPanelProps {
  sessionId: string;
  /** Pre-loaded history from GET /api/session/{id}. */
  initialMessages?: LocalMessage[];
  /** Extra Tailwind classes for the outer container. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Message bubble
// ---------------------------------------------------------------------------

function MessageBubble({ msg }: { msg: LocalMessage }): React.ReactElement {
  const isUser = msg.role === "user";

  return (
    <div className={["flex", isUser ? "justify-end" : "justify-start"].join(" ")}>
      <div className={["max-w-[80%] space-y-2", isUser ? "items-end" : "items-start"].join(" ")}>
        <div
          className={[
            "rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
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

// ---------------------------------------------------------------------------
// Typing indicator
// ---------------------------------------------------------------------------

function TypingIndicator(): React.ReactElement {
  return (
    <div className="flex justify-start">
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

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ChatPanel({
  sessionId,
  initialMessages = [],
  className = "",
}: ChatPanelProps): React.ReactElement {
  const [messages, setMessages] = useState<LocalMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const { mutate: send, isPending } = useMutation({
    mutationFn: ({ message }: { message: string }) =>
      sendChatMessage(sessionId, message),
    onMutate: ({ message }) => {
      // Optimistic user bubble
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
        "flex flex-col rounded-xl border border-[var(--sage-border)] bg-[var(--sage-bg-elevated)]",
        className,
      ].join(" ")}
    >
      {/* Header */}
      <div className="border-b border-[var(--sage-border)] px-4 py-3">
        <h3 className="text-sm font-semibold text-[var(--sage-text-primary)]">
          Chat
        </h3>
        <p className="text-xs text-[var(--sage-text-muted)]">
          Ask anything about your dataset
        </p>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-[300px] max-h-[480px]">
        {messages.length === 0 && (
          <p className="py-8 text-center text-sm text-[var(--sage-text-dim)]">
            No messages yet. Ask a question about your data.
          </p>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
        {isPending && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
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
