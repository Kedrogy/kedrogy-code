import { messageText } from "../i18n/messages";
import { useTranslation } from "react-i18next";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { API } from "../api";
import { parseDeletionPreview, type DeletionPreview } from "../api/operations";
import { isRecord, responseError } from "../api/tasks";
import { LegacyCleanupReview } from "./LegacyCleanupReview";

export function DeletionReview({ target, id, action }: { target: "models" | "datasets"; id: string; action: "model" | "model_files" | "dataset" | "annotations" }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [plan, setPlan] = useState<DeletionPreview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [recordedModelId, setRecordedModelId] = useState<number | null>(null);
  const key = useRef(crypto.randomUUID());
  useEffect(() => {
    const controller = new AbortController();
    setPlan(null);
    const path = action === "annotations" ? "retained_annotations/" : `deletion_preview/?action=${action}`;
    void fetch(`${API}/api/${target}/${id}/${path}`, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]) })
      .then(async r => { if (!r.ok) throw new Error(await responseError(r)); return parseDeletionPreview(await r.json()); })
      .then(p => { setPlan(p); setError(""); })
      .catch((e: unknown) => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Could not load cleanup preview."); });
    return () => controller.abort();
  }, [target, id, action, revision]);
  async function submit() {
    if (!plan || busy) return;
    setBusy(true); setError("");
    try {
      const path = action === "annotations" ? "retained_annotations/" : action === "model_files" ? "delete_model/" : "";
      const response = await fetch(`${API}/api/${target}/${id}/${path}`, {
        method: path ? "POST" : "DELETE", headers: { "Content-Type": "application/json", "Idempotency-Key": key.current },
        body: JSON.stringify({ preview_token: plan.preview_token }), signal: AbortSignal.timeout(15000),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const result: unknown = await response.json();
      if (!isRecord(result) || typeof result.result_id !== "string") throw new Error("The cleanup response is invalid. Retry using the same request.");
      navigate(`/operations/delete/${result.result_id}`);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Cleanup could not be submitted."); }
    finally { setBusy(false); }
  }
  return <main className="max-w-3xl mx-auto p-8 space-y-4">
    <h1 className="text-2xl font-bold">{t(action === "model_files" ? "reviewModelFiles" : action === "annotations" ? "reviewAnnotationsDeletion" : target === "models" ? "reviewModelDeletion" : "reviewDatasetDeletion")}</h1>
    {error && <p role="alert" className="alert alert-error">{messageText(error, t)}</p>}
    {!plan && !error && <p role="status">{t("preparingPreview")}</p>}
    {recordedModelId !== null && <p role="status" className="alert alert-success">{t("ownershipRecorded", { id: recordedModelId })}</p>}
    {plan && <><p>{t("cleanupTarget", { target: t(target === "models" ? "modelNumber" : "datasetNumber", { id }), models: plan.model_ids.map(value => `#${value}`).join(", ") || t("none") })}</p>
      <p>{t(plan.retains_annotations ? "retainSourceAndAnnotations" : "deleteAnnotationsOnly")}</p>
      {action !== "annotations" && <p>{t("checkpointDeletionWarning")}</p>}
      <ul className="list-disc pl-6">{plan.resources.map(r => <li key={`${r.kind}/${r.name}`}>{r.kind}/{r.name}</li>)}</ul>
      {!plan.resources.length && <p>{t(plan.issues.length ? "ownershipUnconfirmed" : "noResourcesToDelete")}</p>}
      {plan.issues.length > 0 && <p className="font-semibold">{t("deletionBlocked")}</p>}
      {plan.issues.map(issue => <p role="alert" key={issue}>{messageText(issue, t)}</p>)}
      {plan.issues.length > 0 && plan.legacy_review_model_ids.map(modelId => <LegacyCleanupReview key={modelId} modelId={modelId}
        onRecorded={() => { setRecordedModelId(modelId); setRevision(value => value + 1); }} />)}
      <button className="btn btn-error" disabled={busy || plan.issues.length > 0} onClick={() => void submit()}>{t(busy ? "submitting" : "confirmCleanup")}</button>
    </>}
    <div className="flex gap-3"><button className="btn" disabled={busy} onClick={() => setRevision(v => v + 1)}>{t("refreshPreview")}</button><Link to="/" className="btn">{t("cancel")}</Link></div>
  </main>;
}
