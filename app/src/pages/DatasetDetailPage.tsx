import { messageText, statusText } from "../i18n/messages";
import { Link, useParams, useNavigate } from "react-router-dom";
import { useEffect, useState, useRef } from "react";
import { useTranslation } from "react-i18next";
import { API } from "../api";
import { parseDataset, parseModel, type Dataset } from "../api/models";
import { isRecord, responseError } from "../api/tasks";

function DatasetDetailPage() {
  const { datasetId } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const labelKey = useRef<string | null>(null);
  const launching = useRef(false);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [error, setError] = useState("");
  const [labels, setLabels] = useState("");
  const [preprocessFun, setPreprocessFun] = useState("");
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const res = await fetch(`${API}/api/datasets/${datasetId}/`, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]) });
        if (!res.ok) throw new Error(await responseError(res));
        const value = parseDataset(await res.json());
        if (!controller.signal.aborted) setDataset(value);
      } catch (err: unknown) { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Could not load dataset."); }
      if (!controller.signal.aborted) timer = setTimeout(() => { void refresh(); }, 5000);
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [datasetId]);

  const handleRename = async () => {
    if (!nameDraft.trim()) return;
    try {
      const res = await fetch(`${API}/api/datasets/${datasetId}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: nameDraft.trim() }),
      });
      if (!res.ok) throw new Error(await responseError(res));
      const data = parseDataset(await res.json());
      setDataset(data);
      setEditingName(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "The request failed.");
    }
  };

  const handleDelete = () => navigate(`/cleanup/datasets/${datasetId}/dataset`);

  const annotationAction = async (action: string) => {
    try {
      const res = await fetch(`${API}/api/datasets/${datasetId}/${action}/`, { method: "POST", signal: AbortSignal.timeout(15000) });
      if (!res.ok) throw new Error(await responseError(res));
      setError("");
    } catch (err: unknown) { setError(err instanceof Error ? err.message : "The annotation action failed."); }
  };

  const handleLabel = async () => {
    if (launching.current) return;
    launching.current = true;
    labelKey.current ??= crypto.randomUUID();
    try {
      const res = await fetch(`${API}/api/datasets/${datasetId}/label/`, { method: "POST", headers: { "Idempotency-Key": labelKey.current }, signal: AbortSignal.timeout(15000) });
      if (!res.ok) throw new Error(await responseError(res));
      const data: unknown = await res.json();
      if (!isRecord(data) || typeof data.result_id !== "string") throw new Error("The annotation response is invalid.");
      labelKey.current = null;
      navigate(`/datasets/task/${data.result_id}`);
    } catch (err: unknown) { setError(err instanceof Error ? err.message : "The request failed."); }
    finally { launching.current = false; }
  };

  const handleCreateModel = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API}/api/models/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          on_dataset: Number(datasetId),
          labels: labels.split(",").map(label => label.trim()),
          a_preprocess_fun: preprocessFun,
        }),
      });
      if (!res.ok) throw new Error(await responseError(res));
      const data = parseModel(await res.json());
      navigate(`/models/${data.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "The request failed.");
    }
  };

  if (!dataset) return <div className="p-8" role={error ? "alert" : "status"}>{error ? messageText(error, t) : t("loading")}</div>;

  return (
    <div className="min-h-screen bg-base-200 p-8">
      <div className="max-w-3xl mx-auto">
      <button onClick={() => navigate("/")} className="btn btn-sm btn-outline mb-6">
        {t("home")}
      </button>

      {editingName ? (
        <div className="flex items-center gap-2 mb-6">
          <input
            className="input input-bordered text-2xl font-bold"
            value={nameDraft}
            onChange={(e) => setNameDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleRename(); if (e.key === "Escape") setEditingName(false); }}
            autoFocus
          />
          <button onClick={handleRename} className="btn btn-primary btn-sm">{t("save")}</button>
          <button onClick={() => setEditingName(false)} className="btn btn-ghost btn-sm">{t("cancel")}</button>
        </div>
      ) : (
        <h1
          className="text-2xl font-bold mb-6 cursor-pointer hover:underline"
          onClick={() => { setNameDraft(dataset.display_name); setEditingName(true); }}
          title={t("renameHint")}
        >
          {t("datasetDetailTitle", { name: dataset.display_name })}
        </h1>
      )}

      {error && <div className="alert alert-error mb-4">{messageText(error, t)}</div>}
      {dataset.pending_cleanup && <Link className="btn mb-4" to={`/operations/delete/${dataset.pending_cleanup}`}>{t("openCleanup")}</Link>}

      {/* Dataset details card */}
      <div className="card bg-base-100 shadow-lg mb-6">
        <div className="card-body">
          <p>{dataset.annotation_policy === "single-label-choice-v2"
            ? t("choicePolicy")
            : t("legacyPolicy")}</p>
          <p>{t("annotationBinding", { status: statusText(dataset.binding_state, t) })}</p>
          {dataset.binding_state === "UNRESOLVED" && <p role="alert">{t("bindingRequired")}</p>}
          <table className="table">
            <tbody>
              <tr><td>{t("dataTable")}</td><td className="text-right">{dataset.data_table_name}</td></tr>
              <tr><td>{t("idField")}</td><td className="text-right">{dataset.id_field}</td></tr>
              <tr><td>{t("image")}</td><td className="text-right">{dataset.image}</td></tr>
              <tr><td>{t("workingDir")}</td><td className="text-right">{dataset.workingDir}</td></tr>
              <tr><td>{t("pipelineName")}</td><td className="text-right">{dataset.pipeline}</td></tr>
              <tr><td>{t("recipeOptions")}</td><td className="text-right">{dataset.recipe_options}</td></tr>
              <tr><td>{t("annotationData")}</td><td>{statusText(dataset.annotation_data.status, t)}</td></tr>
              <tr><td>{t("session")}</td><td>{statusText(dataset.annotation_session.status, t)}</td></tr>
            </tbody>
          </table>
          {dataset.annotation_data.counts && <p>{t("annotationCounts", dataset.annotation_data.counts)}</p>}
          <p>{t("annotationPreflightNote")}</p>
          {dataset.annotation_data.error && <p role="status">{messageText(dataset.annotation_data.error.message, t, dataset.annotation_data.error.code)}</p>}
          {dataset.annotation_session.error && <p role="status">{messageText(dataset.annotation_session.error.message, t, dataset.annotation_session.error.code)}</p>}
          <div className="card-actions mt-4">
            <button className="btn btn-sm" onClick={() => void annotationAction("refresh_annotations")}>{t("refreshCounts")}</button>
            {dataset.annotation_session.url && <a className="btn btn-sm" href={dataset.annotation_session.url} target="_blank" rel="noreferrer">{t("openSession")}</a>}
            {dataset.annotation_session.id && dataset.annotation_session.status !== "STOPPED" && <button className="btn btn-sm" onClick={() => void annotationAction("stop_annotation")}>{t("stopAnnotation")}</button>}
            <button onClick={handleDelete} className="btn btn-error btn-sm">
              {t("delete")}
            </button>
            <button onClick={handleLabel} className="btn btn-primary btn-sm" disabled={dataset.binding_state === "UNRESOLVED" || dataset.deletion_pending || dataset.annotations_deleted || (dataset.annotation_session.id !== null && dataset.annotation_session.status !== "STOPPED")}>
              {t("label")}
            </button>
          </div>
        </div>
      </div>

      {/* New model card */}
      <div className="card bg-base-100 shadow-lg">
        <div className="card-body">
          <h2 className="card-title">{t("newModel")}</h2>
          <form onSubmit={handleCreateModel} className="space-y-4">
            <fieldset className="fieldset">
              <legend className="fieldset-legend">{t("labels")}</legend>
              <input
                className="input input-bordered w-full"
                placeholder={t("labelsPlaceholder")}
                value={labels}
                onChange={(e) => setLabels(e.target.value)}
                required
              />
            </fieldset>
            <fieldset className="fieldset">
              <legend className="fieldset-legend">{t("preprocessingFunction")}</legend>
              <input
                className="input input-bordered w-full"
                placeholder={t("preprocessorPlaceholder")}
                value={preprocessFun}
                onChange={(e) => setPreprocessFun(e.target.value)}
              />
            </fieldset>
            <div className="card-actions justify-end mt-4">
              <button type="submit" className="btn btn-primary" disabled={dataset.binding_state !== "BOUND" || dataset.deletion_pending || dataset.annotations_deleted}>
                {t("newModel")}
              </button>
            </div>
          </form>
        </div>
      </div>
      </div>
    </div>
  );
}

export default DatasetDetailPage;
