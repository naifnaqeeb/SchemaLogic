"use client";

import Link from "next/link";
import { useLanguage } from "@/contexts/LanguageContext";
import { LANGUAGES, isLanguage } from "@/lib/i18n";
import { TranslationNotice } from "@/components/TranslationNotice";

// Matches the Figma reference: amber "Browse All Schemes" link top-left, centered wordmark,
// language menu top-right -- five languages since multilingual stage 3, each named in its own script.
export function NavBar({ active }: { active: "chat" | "browse" }) {
  const { t, language, setLanguage } = useLanguage();

  const toggleButton = (
    <label className="inline-flex items-center gap-2 rounded-full border border-sl-hairline bg-sl-surface px-4 py-1.5 text-sm text-sl-navy shadow-(--sl-shadow) hover:border-sl-accent transition-colors">
      <span aria-hidden="true">🌐</span>
      <select
        aria-label="Language"
        value={language}
        onChange={(e) => isLanguage(e.target.value) && setLanguage(e.target.value)}
        className="bg-transparent outline-none cursor-pointer"
      >
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code} lang={l.code}>
            {l.nativeName}
          </option>
        ))}
      </select>
    </label>
  );

  // Layout differs slightly per page, matching the Figma reference exactly: chat page is a
  // 3-part bar (browse link / centered wordmark / toggle); browse page is just wordmark-left +
  // toggle-right (no redundant "browse" link, no "back to chat" text link -- the floating
  // Ask-AI-Sahayak button covers that).
  if (active === "browse") {
    return (
      <header className="sticky top-0 z-40 bg-sl-surface border-b border-sl-hairline">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <span className="font-bold text-2xl text-sl-navy">SchemeLogic</span>
          {toggleButton}
        </div>
        <TranslationNotice />
      </header>
    );
  }

  return (
    <header className="sticky top-0 z-40 bg-sl-surface border-b border-sl-hairline">
      <div className="max-w-6xl mx-auto px-6 py-4 grid grid-cols-3 items-center">
        <div className="justify-self-start">
          <Link
            href="/browse"
            className="inline-flex items-center gap-1.5 text-sl-accent font-semibold text-[0.95rem] hover:underline"
          >
            🔗 {t("nav_browse")}
          </Link>
        </div>
        <div className="justify-self-center">
          <span className="font-bold text-2xl text-sl-navy">SchemeLogic</span>
        </div>
        <div className="justify-self-end">{toggleButton}</div>
      </div>
      <TranslationNotice />
    </header>
  );
}
