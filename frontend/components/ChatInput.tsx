"use client";

import { useState } from "react";
import { useLanguage } from "@/contexts/LanguageContext";
import { LANGUAGES } from "@/lib/i18n";
import { useSpeechRecognition } from "@/lib/useSpeechRecognition";

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: Props) {
  const { t, language } = useLanguage();
  const speechLang = LANGUAGES.find((l) => l.code === language)?.speech ?? "en-IN";
  const [value, setValue] = useState("");

  const { supported, listening, toggle } = useSpeechRecognition((transcript) => {
    // Writes into React state directly and stops there -- does NOT auto-submit. The citizen
    // reviews/edits and presses Enter or the send button themselves, same as normal typed text;
    // misrecognized speech is never silently sent.
    setValue((prev) => (prev ? `${prev} ${transcript}` : transcript));
  }, speechLang);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  return (
    <div className="sticky bottom-0 z-30 bg-sl-bg pt-2 pb-4">
      <div className="max-w-3xl mx-auto px-4">
        <div className="flex items-center gap-2 rounded-full border border-sl-hairline bg-sl-surface shadow-(--sl-shadow) pl-4 pr-2 py-2">
          <button
            type="button"
            title="Attachments not available yet"
            className="text-sl-muted hover:bg-sl-bg rounded-full w-8 h-8 flex items-center justify-center flex-shrink-0"
          >
            +
          </button>
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder={t("chat_input_placeholder")}
            disabled={disabled}
            className="flex-1 bg-transparent outline-none text-sl-text placeholder:text-sl-muted min-w-0"
          />
          <button
            type="button"
            onClick={toggle}
            title={supported ? "Voice input" : "Voice input not supported in this browser"}
            className={`rounded-full w-8 h-8 flex items-center justify-center flex-shrink-0 ${
              listening ? "text-sl-ineligible" : "text-sl-muted"
            } ${supported ? "hover:bg-sl-bg" : "opacity-40"}`}
          >
            🎤
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={disabled || !value.trim()}
            className="rounded-full w-9 h-9 flex items-center justify-center bg-sl-navy text-white disabled:opacity-40 flex-shrink-0"
          >
            ➤
          </button>
        </div>
        <p className="text-center text-xs text-sl-muted mt-2">{t("disclaimer")}</p>
      </div>
    </div>
  );
}
