"use client";

import Link from "next/link";
import { useLanguage } from "@/contexts/LanguageContext";

// Matches the Figma reference: amber "Browse All Schemes" link top-left, centered wordmark,
// language toggle top-right (stacked "English/हिंदी" style, via CSS line-break on the slash).
export function NavBar({ active }: { active: "chat" | "browse" }) {
  const { t, toggle } = useLanguage();
  const label = t("lang_toggle_label"); // "English/हिंदी" or "हिंदी/English"
  const [first, second] = label.split("/");

  const toggleButton = (
    <button
      type="button"
      onClick={toggle}
      className="inline-flex items-center gap-2 rounded-full border border-sl-hairline bg-sl-surface px-4 py-1.5 text-sm text-sl-navy shadow-(--sl-shadow) hover:border-sl-accent transition-colors"
    >
      <span>🌐</span>
      <span className="leading-tight text-center">
        {first}/<br />
        {second}
      </span>
    </button>
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
    </header>
  );
}
