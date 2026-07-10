/**
 * frontend/src/api/chat.ts
 *
 * Typed wrapper for the conversational Q&A endpoint.
 *
 * sendChatMessage — POST /api/chat
 *
 * The chat endpoint accepts a natural-language question about the active
 * session's data and returns an assistant reply plus an optional Plotly
 * chart if the question triggered a Custom Viz.
 */

import { apiPost } from "./client";
import type { ChatRequest, ChatResponse } from "../types/api";

/**
 * Send a user message to the chat agent and receive a reply.
 *
 * @param sessionId  Active session UUID
 * @param message    Plain-English question from the user
 */
export async function sendChatMessage(
  sessionId: string,
  message: string,
): Promise<ChatResponse> {
  const body: ChatRequest = {
    session_id: sessionId,
    message,
  };
  return apiPost<ChatResponse>("/api/chat", body);
}
