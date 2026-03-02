
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

const resources = {
  en: {
    translation: {
      title: "Datasets & Models",
      yourModels: "Your Models",
      create: "Create",
      noModels: "No models found.",
      prodigyNotRunning: "Prodigy is not running.",
      prodigyRunning: "Prodigy running for dataset {{dataset}}",
      name: "Name",
      dataTable: "Data table",
      idField: "Data table ID field",
      image: "Image",
      workingDir: "Working directory (relative to /app)",
      pipeline: "Pipeline (leave empty for default)",
      recipeOptions: "Prodigy recipe options, space separated",
      creatingDataset: "Creating dataset...",
      labelDataset: "Label Dataset",
      datasetDetails: "You're looking at dataset {{name}}",
      newModel: "New model",
      home: "HOME",
    },
  },
  ru: {
    translation: {
      title: "Датасеты и модели",
      yourModels: "Ваши модели",
      create: "Создать",
      noModels: "Модели не найдены.",
      prodigyNotRunning: "Prodigy не запущен.",
      prodigyRunning: "Prodigy запущен для датасета {{dataset}}",
      name: "Название",
      dataTable: "Таблица данных",
      idField: "Поле ID",
      image: "Образ",
      workingDir: "Рабочая директория (относительно /app)",
      pipeline: "Пайплайн (оставьте пустым по умолчанию)",
      recipeOptions: "Опции рецепта Prodigy через пробел",
      creatingDataset: "Создание датасета...",
      labelDataset: "Разметить датасет",
      datasetDetails: "Вы смотрите на датасет {{name}}",
      newModel: "Новая модель",
      home: "ГЛАВНАЯ",
    },
  },
} as const;

i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: "en",
    fallbackLng: "en",
    interpolation: {
      escapeValue: false,
    },
    react: {
      useSuspense: false,
    },
  });

export default i18n;