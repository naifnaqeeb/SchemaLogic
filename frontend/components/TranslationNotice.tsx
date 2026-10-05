"use client";

import { useLanguage } from "@/contexts/LanguageContext";
import { translate, translationState } from "@/lib/i18n";

// A standing notice under the nav bar, on every page, for any language a person hasn't fully reviewed
// (2026-10-05): "machine" -- machine-translated, unreviewed; "none" -- not translated yet, so mostly
// English. Shown in the selected language when that text exists, always with the English beneath it,
// since the notice's own translation is unreviewed too.
export function TranslationNotice() {
  const { language, t } = useLanguage();
  const state = translationState(language);
  if (state === "reviewed") return null;
  const key = state === "machine" ? "translation_notice_machine" : "translation_notice_none";
  const native = t(key);
  const english = translate(key, "en");
  return (
    <div role="note" className="border-t border-amber-200 bg-amber-50 text-amber-900 text-sm">
      <div className="max-w-6xl mx-auto px-6 py-2">
        <span aria-hidden="true">⚠️ </span>
        <span>{native}</span>
        {native !== english && (
          <span lang="en" dir="ltr" className="block text-xs opacity-80">
            {english}
          </span>
        )}
      </div>
    </div>
  );
}
