"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLanguage } from "@/contexts/LanguageContext";
import { NavBar } from "@/components/NavBar";
import { CategoryPills } from "@/components/CategoryPills";
import { SchemeCard } from "@/components/SchemeCard";
import { FloatingChatButton } from "@/components/FloatingChatButton";
import { getOrCreateSessionId } from "@/lib/session";
import * as api from "@/lib/api";
import type { SchemeRow } from "@/lib/types";

export default function BrowsePage() {
  const { t, language } = useLanguage();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [results, setResults] = useState<SchemeRow[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<string[]>([]);
  const [selecting, setSelecting] = useState<string | null>(null);

  useEffect(() => {
    const handle = setTimeout(() => {
      api
        .listSchemes({ query, category, limit: 60 })
        .then((res) => {
          setResults(res.results);
          setTotal(res.total);
          setCategories(res.categories);
        })
        .catch(() => {
          setResults([]);
          setTotal(0);
        });
    }, 250); // debounce search-as-you-type
    return () => clearTimeout(handle);
  }, [query, category]);

  async function handleSelect(scheme: SchemeRow) {
    const sessionId = getOrCreateSessionId();
    setSelecting(scheme.id);
    try {
      await api.selectScheme(sessionId, scheme.id, scheme.source_type, language);
      router.push("/");
    } catch {
      setSelecting(null);
    }
  }

  return (
    <div className="min-h-screen">
      <NavBar active="browse" />
      <main className="max-w-6xl mx-auto px-6 py-8">
        <h1 className="text-4xl font-bold text-sl-text">{t("browse_title")}</h1>
        <p className="mt-2 text-sl-muted">{t("browse_subtitle")}</p>

        <div className="mt-6 bg-sl-surface border border-sl-hairline rounded-2xl shadow-(--sl-shadow) p-4 space-y-4">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("search_placeholder")}
            className="w-full sm:w-80 rounded-lg border border-sl-hairline px-4 py-2 outline-none focus:border-sl-accent"
          />
          <CategoryPills categories={categories} active={category} onSelect={setCategory} />
        </div>

        <p className="mt-4 text-sm text-sl-muted">
          {total} {t("schemes_shown_suffix")}
        </p>

        <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {results.map((scheme) => (
            <SchemeCard key={`${scheme.source_type}-${scheme.id}`} scheme={scheme} onSelect={() => handleSelect(scheme)} busy={selecting === scheme.id} />
          ))}
        </div>
      </main>
      <FloatingChatButton />
    </div>
  );
}
