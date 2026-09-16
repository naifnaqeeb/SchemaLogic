"use client";

import { useEffect, useRef, useState } from "react";
import { useLanguage } from "@/contexts/LanguageContext";
import { NavBar } from "@/components/NavBar";
import { ChatMessageView } from "@/components/ChatMessageView";
import { ChatInput } from "@/components/ChatInput";
import { ExampleQueryCards } from "@/components/ExampleQueryCards";
import { getOrCreateSessionId, resetSessionId } from "@/lib/session";
import * as api from "@/lib/api";
import type { ChatMessage, ChatResponse } from "@/lib/types";

export default function ChatPage() {
  const { t, language } = useLanguage();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState<ChatResponse["pending_question"]>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const id = getOrCreateSessionId();
    setSessionId(id);
    api
      .getChat(id)
      .then((res) => {
        setMessages(res.messages);
        setPendingQuestion(res.pending_question);
      })
      .catch(() => {
        /* backend not reachable yet -- home still renders, just starts empty */
      });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function applyResponse(res: ChatResponse) {
    setMessages(res.messages);
    setPendingQuestion(res.pending_question);
  }

  async function withBusy(fn: () => Promise<ChatResponse>) {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fn();
      applyResponse(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong talking to the API.");
    } finally {
      setBusy(false);
    }
  }

  const handleSend = (text: string) => sessionId && withBusy(() => api.sendMessage(sessionId, text, language));
  const handleQuickReply = (reply: string) => sessionId && withBusy(() => api.sendQuickReply(sessionId, reply, language));
  const handleSelectScheme = (schemeId: string, sourceType: string) =>
    sessionId && withBusy(() => api.selectScheme(sessionId, schemeId, sourceType, language));
  const handleReset = () => {
    const fresh = resetSessionId();
    setSessionId(fresh);
    setMessages([]);
    setPendingQuestion(null);
  };

  const hasPendingLive = pendingQuestion !== null;

  return (
    <div className="flex flex-col min-h-screen">
      <NavBar active="chat" />
      <main className="flex-1 max-w-3xl w-full mx-auto px-4 py-6 space-y-4">
        {messages.length === 0 ? (
          <>
            <div className="flex justify-start gap-3">
              <div className="flex-shrink-0 w-9 h-9 rounded-full bg-sl-navy text-white flex items-center justify-center text-sm">🤖</div>
              <div className="max-w-2xl rounded-2xl px-4 py-3 shadow-(--sl-shadow) bg-sl-surface">{t("greeting")}</div>
            </div>
            <ExampleQueryCards onSelect={handleSend} busy={busy} />
            <p
              className="text-sm text-sl-muted"
              dangerouslySetInnerHTML={{ __html: t("browse_hint").replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>") }}
            />
          </>
        ) : (
          <>
            {messages.map((msg, i) => (
              <ChatMessageView
                key={i}
                message={msg}
                isLivePending={i === messages.length - 1 && hasPendingLive}
                onQuickReply={handleQuickReply}
                onSelectScheme={handleSelectScheme}
                busy={busy}
              />
            ))}
            <div ref={bottomRef} />
            <div className="pt-2">
              <button
                type="button"
                onClick={handleReset}
                className="rounded-lg border border-sl-hairline px-4 py-2 text-sm font-medium hover:border-sl-accent transition-colors"
              >
                {t("start_over")}
              </button>
            </div>
          </>
        )}
        {error && <p className="text-sm text-sl-ineligible">{error}</p>}
      </main>
      <ChatInput onSend={handleSend} disabled={busy || !sessionId} />
    </div>
  );
}
