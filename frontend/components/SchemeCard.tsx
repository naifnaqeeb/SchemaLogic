"use client";

import { useLanguage } from "@/contexts/LanguageContext";
import { Seal } from "./Seal";
import type { SchemeRow } from "@/lib/types";

interface Props {
  scheme: SchemeRow;
  onSelect: () => void;
  busy?: boolean;
}

export function SchemeCard({ scheme, onSelect, busy }: Props) {
  const { t } = useLanguage();
  const snippet = scheme.description ? scheme.description.slice(0, 140) + (scheme.description.length > 140 ? "..." : "") : null;

  return (
    <div className="bg-sl-surface border border-sl-hairline border-l-4 border-l-sl-accent rounded-xl shadow-(--sl-shadow) p-5 flex flex-col gap-2 hover:-translate-y-0.5 hover:shadow-md transition-all">
      <h3 className="font-semibold text-sl-navy">{scheme.name}</h3>
      <Seal tier={scheme.source_type} />
      {snippet && <p className="text-sm text-sl-muted flex-1">{snippet}</p>}
      <button
        type="button"
        onClick={onSelect}
        disabled={busy}
        className="mt-2 self-start rounded-lg border border-sl-hairline px-4 py-2 text-sm font-medium text-sl-navy hover:border-sl-accent transition-colors disabled:opacity-50"
      >
        {t("view_details")} →
      </button>
    </div>
  );
}
