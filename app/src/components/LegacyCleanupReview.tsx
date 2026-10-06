import { messageText } from "../i18n/messages";
import { useTranslation } from "react-i18next";
import { useState } from "react";
import { API } from "../api";
import { parseLegacyCleanupReview, type LegacyCleanupReview as Review } from "../api/operations";
import { isRecord, responseError } from "../api/tasks";

export function LegacyCleanupReview({ modelId, onRecorded }: {modelId: number; onRecorded: () => void}) {
  const { t } = useTranslation();
  const [review, setReview] = useState<Review | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const path = `${API}/api/models/${modelId}/legacy_cleanup_review/`;
  async function inspect() {
    setBusy(true); setError(""); setConfirmed(false); setReview(null);
    try {
      const response = await fetch(path, {signal: AbortSignal.timeout(60000)});
      if (!response.ok) throw new Error(await responseError(response));
      const value = parseLegacyCleanupReview(await response.json());
      if (value.model_id !== modelId) throw new Error("The review belongs to a different model.");
      setReview(value);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Could not inspect legacy resources."); }
    finally { setBusy(false); }
  }
  async function record() {
    if (!review || !confirmed || review.issues.length || busy) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({review_token: review.review_token}), signal: AbortSignal.timeout(60000)});
      if (!response.ok) throw new Error(await responseError(response));
      const value: unknown = await response.json();
      if (!isRecord(value) || value.recorded !== true || value.deleted !== false || value.model_id !== modelId) {
        throw new Error("The ownership review response is invalid. Refresh the preview.");
      }
      onRecorded();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Ownership could not be recorded."); }
    finally { setBusy(false); }
  }
  return <section className="rounded-box border border-base-300 p-5 space-y-3" aria-label={t("legacyReviewLabel", { id: modelId })}>
    <h2 className="font-bold">{t("legacyReviewTitle", { id: modelId })}</h2>
    <p>{t("legacyReviewNote")}</p>
    <button type="button" className="btn" disabled={busy} onClick={() => void inspect()}>{t(busy ? "checking" : review ? "checkResourcesAgain" : "checkLegacyResources")}</button>
    {error && <p role="alert" className="alert alert-error">{messageText(error, t)}</p>}
    {review && <>
      <ul className="list-disc pl-6">{review.evidence.map(value => <li key={value}>{messageText(value, t)}</li>)}</ul>
      <details><summary>{t("resourceIdentities", { count: review.resources.length })}</summary>
        <ul>{review.resources.map(r => <li key={`${r.kind}/${r.name}`} className="break-all">{r.kind}/{r.name} · {r.namespace} · {t("resourceUid", { uid: r.uid })}</li>)}</ul>
      </details>
      {review.issues.map(value => <p key={value} role="alert">{messageText(value, t)}</p>)}
      {!review.issues.length && <>
        <label className="flex items-start gap-3"><input type="checkbox" className="checkbox" checked={confirmed} disabled={busy}
          onChange={event => setConfirmed(event.target.checked)} />
          <span>{t("confirmLegacyOwnership", { id: modelId })}</span>
        </label>
        <button type="button" className="btn btn-primary" disabled={!confirmed || busy} onClick={() => void record()}>{t("recordOwnership")}</button>
      </>}
    </>}
  </section>;
}
