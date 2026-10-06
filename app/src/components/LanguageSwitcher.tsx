import { useTranslation } from "react-i18next";

export function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  return <div className="navbar bg-base-100 shadow-sm">
    <div className="flex-1"><span className="text-xl font-bold px-4">Kedrogy</span></div>
    <div className="flex-none gap-2 pr-4" role="group" aria-label={t("language")}>
      {(["en", "ru"] as const).map(language => <button key={language} type="button"
        lang={language} aria-label={language === "en" ? "English" : "Русский"}
        aria-pressed={i18n.resolvedLanguage === language}
        className={`btn btn-sm ${i18n.resolvedLanguage === language ? "btn-primary" : "btn-outline"}`}
        onClick={() => void i18n.changeLanguage(language)}>{language.toUpperCase()}</button>)}
    </div>
  </div>;
}
