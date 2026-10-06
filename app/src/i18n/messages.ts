import type { TFunction } from "i18next";
import { en } from "./catalog.ts";
import { publicMessagesRu } from "./publicMessages.ts";

export function statusText(status: string, t: TFunction): string {
  const key = `status${status}`;
  return Object.hasOwn(en, key) ? t(key) : t("unknownStatus");
}

const fields: Record<string, string> = {
  dataset_name: "name", display_name: "name", model_name: "name", labels: "labels",
  data_table_name: "dataTable", id_field: "idField", image: "image", workingDir: "workingDir",
  pipeline: "pipelineName", recipe_options: "recipeOptions", a_preprocess_fun: "preprocessingFunction",
  on_dataset: "datasets", text_input: "textInput", annotation_policy: "annotationData",
};

const dynamicMessages = Object.keys(publicMessagesRu).filter(key => key.includes("{{"))
  .map(key => ({
    key,
    parameters: [...key.matchAll(/\{\{(\w+)\}\}/g)].map(match => match[1]),
    expression: new RegExp("^" + key.split(/\{\{\w+\}\}/)
      .map(part => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("(.+?)") + "$"),
  }));

export function messageText(message: string, t: TFunction, code?: string): string {
  if (!message) return "";
  if (Object.hasOwn(publicMessagesRu, message)) {
    return t(message, { ns: "messages", keySeparator: false, nsSeparator: false });
  }
  for (const { key, expression, parameters } of dynamicMessages) {
    const match = expression.exec(message);
    if (match) return t(key, { ns: "messages", keySeparator: false, nsSeparator: false,
      ...Object.fromEntries(parameters.map((name, index) => [name, match[index + 1]])) });
  }
  // Validation fields are joined by the API adapter. Keep their individual reasons.
  const fieldPattern = new RegExp(`(?:^| )(${Object.keys(fields).join("|")}): `, "g");
  const matches = [...message.matchAll(fieldPattern)];
  if (matches.length) return matches.map((match, index) => {
    const start = match.index + match[0].length;
    const end = matches[index + 1]?.index ?? message.length;
    return `${t(fields[match[1]])}: ${messageText(message.slice(start, end).trim(), t)}`;
  }).join(" ");
  if (/^[^A-Za-z]*[А-Яа-яЁё]/.test(message)) return message;
  return t(code ? "unrecognizedErrorCode" : "unrecognizedMessage", { message, code });
}
