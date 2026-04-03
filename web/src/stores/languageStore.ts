import { create } from "zustand";

const LOCALE_KEY = "biocoach_locale";

type Locale = "ru" | "en";

function detectLocale(): Locale {
  try {
    const stored = localStorage.getItem(LOCALE_KEY);
    if (stored === "ru" || stored === "en") return stored;
  } catch {
    // localStorage unavailable (SSR, private mode)
  }
  try {
    if (navigator.language.startsWith("ru")) return "ru";
  } catch {
    // navigator unavailable
  }
  return "en";
}

interface LanguageState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
}

export const useLanguageStore = create<LanguageState>((set) => ({
  locale: detectLocale(),
  setLocale: (locale: Locale) => {
    try {
      localStorage.setItem(LOCALE_KEY, locale);
    } catch {
      // localStorage unavailable
    }
    set({ locale });
  },
}));
