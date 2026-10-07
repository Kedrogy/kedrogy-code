import { messageText } from "../i18n/messages";
import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { API } from "../api";
import { parseDataset, type Dataset } from "../api/models";
import { responseError } from "../api/tasks";

export default function RetainedAnnotationsPage() {
  const { t } = useTranslation();
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void fetch(`${API}/api/datasets/?retired=true`, { signal: controller.signal })
      .then(async r => { if (!r.ok) throw new Error(await responseError(r)); const value: unknown = await r.json(); if (!Array.isArray(value)) throw new Error("Invalid dataset list."); return value.map(parseDataset); })
      .then(setDatasets).catch((e: unknown) => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Could not load retained bindings."); });
    return () => controller.abort();
  }, []);
  return <main className="max-w-3xl mx-auto p-8 space-y-4"><h1 className="text-2xl font-bold">{t("retainedBindings")}</h1>
    <p>{t("retainedBindingsNote")}</p>{error && <p role="alert">{messageText(error, t)}</p>}
    {datasets.map(d => <div className="card bg-base-100 p-4" key={d.id}><p>{d.display_name} — {t(d.annotations_deleted ? "annotationsDeleted" : "annotationsRetained")}</p>
      {!d.annotations_deleted && d.binding_state === "BOUND" && <Link to={`/cleanup/datasets/${d.id}/annotations`} className="btn">{t("reviewAnnotationDeletion")}</Link>}</div>)}
    <Link to="/">{t("home")}</Link></main>;
}
