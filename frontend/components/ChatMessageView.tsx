"use client";

import { useLanguage } from "@/contexts/LanguageContext";
import { Seal } from "./Seal";
import { NextStepsView } from "./NextStepsView";
import type { ChatMessage } from "@/lib/types";

const VERDICT_STYLES: Record<string, string> = {
  eligible: "border-sl-verified bg-sl-verified/10 text-sl-verified",
  ineligible: "border-sl-ineligible bg-sl-ineligible/10 text-sl-ineligible",
};
const VERDICT_FALLBACK = "border-sl-warrant bg-sl-warrant/10 text-sl-warrant";

function Bubble({ role, children }: { role: "user" | "assistant"; children: React.ReactNode }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} gap-3`}>
      {!isUser && (
        <div className="flex-shrink-0 w-9 h-9 rounded-full bg-sl-navy text-white flex items-center justify-center text-sm">🤖</div>
      )}
      <div
        className={`max-w-2xl rounded-2xl px-4 py-3 shadow-(--sl-shadow) ${
          isUser ? "bg-sl-accent-soft text-sl-text" : "bg-sl-surface text-sl-text"
        }`}
      >
        {children}
      </div>
    </div>
  );
}

interface Props {
  message: ChatMessage;
  isLivePending: boolean;
  onQuickReply: (reply: string) => void;
  onSelectScheme: (schemeId: string, sourceType: string) => void;
  busy: boolean;
}

export function ChatMessageView({ message, isLivePending, onQuickReply, onSelectScheme, busy }: Props) {
  const { t } = useLanguage();

  switch (message.kind) {
    case "text":
      return (
        <Bubble role={message.role}>
          <p className="whitespace-pre-wrap">{message.text}</p>
        </Bubble>
      );

    case "scheme_intro":
      return (
        <Bubble role="assistant">
          <div className="flex items-center gap-2 flex-wrap">
            <span>{message.text}</span>
            <Seal tier={message.tier ?? "silver"} />
          </div>
        </Bubble>
      );

    case "shortlist":
      return (
        <Bubble role="assistant">
          <p className="mb-3">{message.text}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            {(message.items ?? []).map((item) => {
              const title = item.text.split(".")[0];
              const snippet = item.text.includes(".") ? item.text.split(".").slice(1).join(".").trim() : "";
              return (
                <div
                  key={item.doc_id}
                  className="border border-sl-hairline border-l-4 border-l-sl-accent rounded-xl p-4 bg-sl-bg/40 flex flex-col gap-2"
                >
                  <div className="font-semibold text-sl-navy">{title}</div>
                  <Seal tier={item.source_type} />
                  {snippet && <p className="text-xs text-sl-muted line-clamp-3">{snippet.slice(0, 180)}</p>}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => onSelectScheme(item.scheme_id, item.source_type)}
                    className="mt-auto self-start rounded-lg border border-sl-hairline px-3 py-1.5 text-sm font-medium text-sl-navy hover:border-sl-accent transition-colors disabled:opacity-50"
                  >
                    {t("select")}
                  </button>
                </div>
              );
            })}
          </div>
        </Bubble>
      );

    case "question":
      return (
        <Bubble role="assistant">
          <p>{message.text}</p>
          {isLivePending && message.quick_replies && message.quick_replies.length > 0 && (
            <div className="flex gap-2 mt-3 flex-wrap">
              {message.quick_replies.map((reply) => (
                <button
                  key={reply}
                  type="button"
                  disabled={busy}
                  onClick={() => onQuickReply(reply)}
                  className="rounded-lg border border-sl-hairline px-4 py-1.5 text-sm font-medium hover:border-sl-accent transition-colors disabled:opacity-50"
                >
                  {reply}
                </button>
              ))}
            </div>
          )}
        </Bubble>
      );

    case "verdict": {
      const verdictClass = VERDICT_STYLES[message.verdict_value ?? ""] ?? VERDICT_FALLBACK;
      return (
        <Bubble role="assistant">
          <p>{message.text}</p>
          <div className={`mt-2 rounded-lg border px-4 py-2.5 font-semibold ${verdictClass}`}>{message.headline}</div>
          <div className="mt-2">
            <Seal tier={message.tier ?? "gold"} />
          </div>
          {message.tier === "ai_checked" && (
            <div className="mt-2 rounded-lg border border-sl-ai-checked bg-sl-ai-checked/10 text-sl-ai-checked px-4 py-2.5 text-sm">
              {t("ai_checked_verdict_disclaimer")}
            </div>
          )}
          {message.plain_explanation && (
            <details className="mt-3 rounded-lg border border-sl-hairline p-3">
              <summary className="cursor-pointer font-medium text-sl-navy">Why? (plain-language explanation)</summary>
              <p className="mt-2 whitespace-pre-wrap text-sm">{message.plain_explanation}</p>
            </details>
          )}
          {message.trace && (
            <details className="mt-2 rounded-lg border border-sl-hairline p-3">
              <summary className="cursor-pointer font-medium text-sl-navy">Technical detail (field names, raw trace)</summary>
              <pre className="mt-2 text-xs font-mono overflow-x-auto whitespace-pre-wrap">{JSON.stringify(message.trace, null, 2)}</pre>
            </details>
          )}
          <NextStepsView nextSteps={message.next_steps} />
        </Bubble>
      );
    }

    case "scheme_detail": {
      const record = message.record ?? {};
      return (
        <Bubble role="assistant">
          <Seal tier="silver" />
          <div className="mt-2 rounded-lg border border-sl-warrant bg-sl-warrant/10 text-sl-warrant px-4 py-2.5 text-sm">
            This scheme hasn&apos;t been verified by our system, and automatic rule extraction either wasn&apos;t attempted or
            didn&apos;t produce a usable result — here&apos;s what&apos;s listed on the government&apos;s myScheme portal. Please
            confirm the details directly with the official source before relying on them.
          </div>
          <h3 className="mt-3 font-semibold text-sl-navy text-lg">{record.scheme_name ?? message.scheme_id}</h3>
          {record.description && <p className="mt-1 text-sm">{record.description}</p>}
          {record.eligibility_text && (
            <div className="mt-2">
              <span className="font-medium text-sm">Eligibility (as listed):</span>
              <p className="text-sm">{record.eligibility_text}</p>
            </div>
          )}
          <NextStepsView nextSteps={message.next_steps} />
        </Bubble>
      );
    }

    default:
      return null;
  }
}
