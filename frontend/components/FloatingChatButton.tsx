"use client";

import Link from "next/link";
import { useLanguage } from "@/contexts/LanguageContext";

export function FloatingChatButton() {
  const { t } = useLanguage();
  return (
    <Link
      href="/"
      className="fixed right-6 bottom-6 z-50 inline-flex items-center gap-2 rounded-full bg-sl-navy text-white px-5 py-3 font-semibold shadow-[0_4px_14px_rgba(15,27,61,0.35)] hover:-translate-y-0.5 transition-transform"
    >
      💬 {t("ask_ai_sahayak")}
    </Link>
  );
}
