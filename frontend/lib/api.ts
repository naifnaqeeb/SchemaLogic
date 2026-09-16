// Thin fetch wrapper around the FastAPI backend. No business logic here -- every function is a
// direct 1:1 call to one endpoint in api/main.py.

import type { ChatResponse, ExampleCard, SchemeListResponse, SchemeRow } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${path} failed (${res.status}): ${detail}`);
  }
  return res.json() as Promise<T>;
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${path} failed (${res.status}): ${detail}`);
  }
  return res.json() as Promise<T>;
}

export function sendMessage(sessionId: string, message: string, language: string): Promise<ChatResponse> {
  return postJSON("/chat", { session_id: sessionId, message, language });
}

export function sendQuickReply(sessionId: string, reply: string, language: string): Promise<ChatResponse> {
  return postJSON("/chat/quick_reply", { session_id: sessionId, reply, language });
}

export function selectScheme(
  sessionId: string,
  schemeId: string,
  sourceType: string,
  language: string,
): Promise<ChatResponse> {
  return postJSON("/chat/select", { session_id: sessionId, scheme_id: schemeId, source_type: sourceType, language });
}

export function selectExample(sessionId: string, label: string, language: string): Promise<ChatResponse> {
  return postJSON("/chat/example", { session_id: sessionId, label, language });
}

export function resetChat(sessionId: string): Promise<ChatResponse> {
  return postJSON("/chat/reset", { session_id: sessionId });
}

export function getChat(sessionId: string): Promise<ChatResponse> {
  return getJSON(`/chat/${encodeURIComponent(sessionId)}`);
}

export function listExamples(): Promise<ExampleCard[]> {
  return getJSON("/examples");
}

export function listSchemes(params: {
  query?: string;
  category?: string;
  limit?: number;
  offset?: number;
}): Promise<SchemeListResponse> {
  const search = new URLSearchParams();
  if (params.query) search.set("query", params.query);
  if (params.category) search.set("category", params.category);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  return getJSON(`/schemes?${search.toString()}`);
}

export function getScheme(id: string): Promise<SchemeRow> {
  return getJSON(`/schemes/${encodeURIComponent(id)}`);
}
