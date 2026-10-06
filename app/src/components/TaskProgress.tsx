import { messageText, statusText } from "../i18n/messages";
import { useTranslation } from "react-i18next";
import { useState } from "react";
import { API } from "../api";
import { responseError } from "../api/tasks";
import { Link } from "react-router-dom";
import type { TaskKind } from "../api/tasks";
import { useTaskStatus } from "../hooks/useTaskStatus";
import { OperationLog } from "./OperationLog";

interface Props {
  kind: TaskKind;
  resultId: string | undefined;
  title: string;
  backTo: string;
}

export function TaskProgress({ kind, resultId, title, backTo }: Props) {
  const { t } = useTranslation();
  const { result, connectionError, retry } = useTaskStatus(kind, resultId);
  const [retryError, setRetryError] = useState("");
  const [retrying, setRetrying] = useState(false);
  async function resume() {
    setRetrying(true);
    try {
      const r = await fetch(`${API}/api/operations/delete/${resultId}/retry/`, { method: "POST", signal: AbortSignal.timeout(15000) });
      if (!r.ok) throw new Error(await responseError(r));
      setRetryError(""); retry();
    } catch (e: unknown) { setRetryError(e instanceof Error ? e.message : "Could not resume cleanup."); }
    finally { setRetrying(false); }
  }
  const succeeded = result?.status === "SUCCEEDED";
  const failed = result?.is_finished && !succeeded;
  return <main className="min-h-screen bg-base-200 p-8">
    <div className="max-w-3xl mx-auto">
      <Link to={backTo} className="btn btn-sm btn-outline mb-6">{t("back")}</Link>
      <section className="card bg-base-100 shadow-lg"><div className="card-body">
        <h1 className="card-title">{title}</h1>
        <p role="status" aria-live="polite">{t("statusLabel")} <span className="badge">{result ? statusText(result.status, t) : t(connectionError ? "unavailable" : "connecting")}</span></p>
        {result?.step && <p>{messageText(result.step, t)}</p>}
        {result?.progress && <p>{t("completedSteps", result.progress)}</p>}
        {result?.can_retry && kind === "delete" && <button className="btn" disabled={retrying} onClick={() => void resume()}>{t("retryCleanup")}</button>}
        {retryError && <p role="alert">{messageText(retryError, t)}</p>}
        {!resultId && <p role="alert">{t("missingTaskId")}</p>}
        {succeeded && <p className="alert alert-success">{t("operationSucceeded")}</p>}
        {failed && <div role="alert" className="alert alert-error">{result.error ? messageText(result.error.message, t, result.error.code) : t("operationFailed")}</div>}
        {failed && !result.can_retry && <p>{t("retryConfiguration")}</p>}
        {result?.session?.dataset_id && <Link className="btn" to={`/datasets/${result.session.dataset_id}`}>{t("viewAnnotationSession")}</Link>}
        {connectionError && <div role="alert" className="alert alert-warning">
          <span>{t("statusRefreshFailed", { message: messageText(connectionError, t) })}</span>
          <button className="btn btn-sm" onClick={retry}>{t("retryStatus")}</button>
        </div>}
        {(kind === "train" || result?.logs) && <OperationLog key={`${kind}:${resultId}`} logs={result?.logs ?? ""}
          finished={result?.is_finished ?? false} training={kind === "train"} />}
        {result?.is_finished && <Link to={backTo} className="btn btn-primary">{t("returnToResults")}</Link>}
      </div></section>
    </div>
  </main>;
}
