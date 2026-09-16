"use client";

import { useLanguage } from "@/contexts/LanguageContext";

interface Props {
  categories: string[];
  active: string;
  onSelect: (category: string) => void;
}

export function CategoryPills({ categories, active, onSelect }: Props) {
  const { t } = useLanguage();
  const pills = [{ id: "all", labelKey: "category_all" }, ...categories.map((c) => ({ id: c, labelKey: `category_${c}` }))];

  return (
    <div className="flex flex-wrap gap-2">
      {pills.map((pill) => {
        const isActive = active === pill.id;
        return (
          <button
            key={pill.id}
            type="button"
            onClick={() => onSelect(pill.id)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium border transition-colors ${
              isActive
                ? "bg-sl-navy border-sl-navy text-white"
                : "bg-sl-surface border-sl-hairline text-sl-text hover:border-sl-accent"
            }`}
          >
            {t(pill.labelKey)}
          </button>
        );
      })}
    </div>
  );
}
