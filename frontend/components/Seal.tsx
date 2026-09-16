"use client";

import { useLanguage } from "@/contexts/LanguageContext";

// The signature verification motif -- circular ring badge, three tiers. Mirrors
// schemelogic/conversational/shared.py's render_seal() exactly (same tiers, same colors, same
// glyphs) -- this is this project's core trust signal, kept even where the reference design
// doesn't show one (browse cards), per explicit instruction not to drop it for pixel-parity.
export function Seal({ tier }: { tier: string }) {
  const { t } = useLanguage();

  const config =
    tier === "gold"
      ? { color: "text-sl-verified", glyph: "✓", labelKey: "seal_verified" }
      : tier === "ai_checked"
        ? { color: "text-sl-ai-checked", glyph: "AI", labelKey: "seal_ai_checked" }
        : { color: "text-sl-warrant", glyph: "!", labelKey: "seal_unverified" };

  return (
    <span className={`inline-flex items-center gap-1.5 text-sm font-medium ${config.color}`}>
      <span className="inline-flex items-center justify-center w-6 h-6 rounded-full border-2 border-current text-xs font-mono flex-shrink-0">
        {config.glyph}
      </span>
      {t(config.labelKey)}
    </span>
  );
}
