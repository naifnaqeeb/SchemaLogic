"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Language } from "@/lib/i18n";
import { LANGUAGES, isLanguage, translate } from "@/lib/i18n";

const STORAGE_KEY = "schemelogic_language";

interface LanguageContextValue {
  language: Language;
  toggle: () => void; // English <-> Hindi, as before
  setLanguage: (language: Language) => void;
  t: (key: string) => string;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>("en");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isLanguage(stored)) setLanguageState(stored);
  }, []);

  // Right-to-left layout for Urdu, and the page's language for screen readers and fonts.
  useEffect(() => {
    const meta = LANGUAGES.find((l) => l.code === language);
    document.documentElement.lang = language;
    document.documentElement.dir = meta?.dir ?? "ltr";
  }, [language]);

  const setLanguage = useCallback((next: Language) => {
    window.localStorage.setItem(STORAGE_KEY, next);
    setLanguageState(next);
  }, []);

  const toggle = useCallback(() => {
    setLanguageState((prev) => {
      const next: Language = prev === "en" ? "hi" : "en";
      window.localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }, []);

  const t = useCallback((key: string) => translate(key, language), [language]);

  const value = useMemo(() => ({ language, toggle, setLanguage, t }), [language, toggle, setLanguage, t]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLanguage must be used within a LanguageProvider");
  return ctx;
}
