import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { en, ru } from "./catalog.ts";
import { publicMessagesRu } from "./publicMessages.ts";

export function savedLanguage(): "en" | "ru" {
  try {
    const language = localStorage.getItem("kedrogy.language");
    if (language === "en" || language === "ru") return language;
  } catch { /* Storage can be disabled by the browser. */ }
  return typeof navigator !== "undefined" && navigator.language.startsWith("ru") ? "ru" : "en";
}

function applyLanguage(language: string) {
  const locale = language.startsWith("ru") ? "ru" : "en";
  if (typeof document !== "undefined") document.documentElement.lang = locale;
  try { localStorage.setItem("kedrogy.language", locale); }
  catch { /* Translation still works when preferences cannot be persisted. */ }
}

i18n.on("languageChanged", applyLanguage);
void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en, messages: Object.fromEntries(Object.keys(publicMessagesRu).map(key => [key, key])) },
    ru: { translation: ru, messages: publicMessagesRu },
  },
  defaultNS: "translation",
  lng: savedLanguage(),
  supportedLngs: ["en", "ru"],
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  react: { useSuspense: false },
});

export default i18n;
