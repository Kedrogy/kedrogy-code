import { messageText, statusText } from "../i18n/messages";
import { Link, useParams, useNavigate } from "react-router-dom";
import { useEffect, useState, useRef } from "react";
import { useTranslation } from "react-i18next";
import { createLatestRequest } from "../api/latestRequest";
import { API } from "../api";
import { isRecord, responseError } from "../api/tasks";

import { parseModel, parsePrediction, parseRuns, type Model, type TrainingRun } from "../api/models";

function ModelDetailPage() {
  const { modelId } = useParams<{ modelId: string }>();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();

  const serveKey = useRef<string | null>(null);
  const [history, setHistory] = useState<TrainingRun[]>([]);
  const [healthError, setHealthError] = useState("");
  const [predicting, setPredicting] = useState(false);
  const requestKey = useRef<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [model, setModel] = useState<Model | null>(null);
  const [textInput, setTextInput] = useState("");
  const [prediction, setPrediction] = useState<{ label: string; text: string; context: string } | null>(null);
  const [predictionError, setPredictionError] = useState("");
  const predictionRequest = useRef(createLatestRequest());
  const predictionContext = JSON.stringify([modelId, model?.id, model?.serving.id,
    model?.serving.training_run_id, model?.serving.status, !!healthError]);
  const [previousPredictionContext, setPreviousPredictionContext] = useState(predictionContext);

  if (previousPredictionContext !== predictionContext) {
    setPreviousPredictionContext(predictionContext);
    setPrediction(null);
    setPredictionError("");
    setPredicting(false);
  }

  useEffect(() => {
    const requests = predictionRequest.current;
    requests.cancel();
    return () => requests.cancel();
  }, [predictionContext]);

  const changeText = (text: string) => {
    predictionRequest.current.cancel();
    setTextInput(text);
    setPrediction(null);
    setPredictionError("");
    setPredicting(false);
  };
  const [error, setError] = useState("");
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [editingLabels, setEditingLabels] = useState(false);
  const [labelsDraft, setLabelsDraft] = useState("");

  useEffect(() => {
    if (!modelId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const response = await fetch(`${API}/api/models/${modelId}/`, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]) });
        if (!response.ok) throw new Error(await responseError(response));
        const data = parseModel(await response.json());
        if (controller.signal.aborted) return;
        setModel(data);
        setHealthError("");
        const runs = await fetch(`${API}/api/models/${modelId}/runs/`, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]) });
        if (runs.ok) setHistory(parseRuns(await runs.json()));
      } catch (error: unknown) {
        if (!controller.signal.aborted) setHealthError(error instanceof Error ? error.message : "Serving health is unavailable.");
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(refresh, 5000);
      }
    };
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [modelId]);

  const handleRenameName = async () => {
    if (!nameDraft.trim()) return;
    try {
      const res = await fetch(`${API}/api/models/${modelId}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_name: nameDraft.trim() }),
      });
      if (!res.ok) throw new Error(await responseError(res));
      const data = parseModel(await res.json());
      setModel(data);
      setEditingName(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "The request failed.");
    }
  };

  const handleRenameLabels = async () => {
    if (!labelsDraft.trim()) return;
    try {
      const res = await fetch(`${API}/api/models/${modelId}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ labels: labelsDraft.split(",").map(label => label.trim()) }),
      });
      if (!res.ok) throw new Error(await responseError(res));
      const data = parseModel(await res.json());
      setModel(data);
      setEditingLabels(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "The request failed.");
    }
  };

  const handleTrain = async () => {
    if (submitting) return;
    if (model?.last_training_run && !model.last_training_run.is_finished) {
      navigate(`/models/${modelId}/train/${model.last_training_run.id}`);
      return;
    }
    requestKey.current ??= crypto.randomUUID();
    setSubmitting(true);
    try {
      const res = await fetch(`${API}/api/models/${modelId}/train/`, {
        method: "POST", headers: { "Idempotency-Key": requestKey.current },
      });
      if (!res.ok) {
        if (res.status < 500) requestKey.current = null;
        throw new Error(await responseError(res));
      }
      const data: unknown = await res.json();
      if (!isRecord(data) || typeof data.result_id !== "string") throw new Error("The training response is invalid.");
      requestKey.current = null;
      navigate(`/models/${modelId}/train/${data.result_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not start training.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleServe = async () => {
    if (submitting) return;
    setSubmitting(true);
    serveKey.current ??= crypto.randomUUID();
    try {
      const res = await fetch(`${API}/api/models/${modelId}/serve/`, { method: "POST", headers: { "Idempotency-Key": serveKey.current } });
      if (!res.ok) {
        if (res.status < 500) serveKey.current = null;
        throw new Error(await responseError(res));
      }
      const data: unknown = await res.json();
      if (!isRecord(data) || typeof data.result_id !== "string") throw new Error("The serving response is invalid.");
      serveKey.current = null;
      navigate(`/models/${modelId}/serve/${data.result_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not start serving.");
    } finally { setSubmitting(false); }
  };

  const handleStop = async () => {
    if (submitting) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${API}/api/models/${modelId}/stop/`, { method: "POST" });
      if (!res.ok) throw new Error(await responseError(res));
      setModel(current => current ? { ...current, served: false, serving: { ...current.serving, status: "STOPPING" } } : null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not stop serving.");
    } finally { setSubmitting(false); }
  };

  const handleDelete = () => navigate(`/cleanup/models/${modelId}/model_files`);

  const handlePredict = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!modelId || model?.id !== Number(modelId) || !model.served || healthError || predicting || !textInput.trim()) return;
    const request = predictionRequest.current.start();
    const submittedText = textInput;
    const submittedContext = predictionContext;
    setPredicting(true);
    setPrediction(null);
    setPredictionError("");
    try {
      const response = await fetch(`${API}/api/models/${modelId}/predict/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text_input: submittedText }),
        signal: request.signal,
      });
      if (!response.ok) throw new Error(await responseError(response));
      const data = await response.json();
      const label = parsePrediction(data, model.serving);
      if (request.isCurrent()) setPrediction({ label, text: submittedText, context: submittedContext });
    } catch (err: unknown) {
      if (request.isCurrent()) setPredictionError(err instanceof Error ? err.message : "The request failed.");
    } finally { if (request.isCurrent()) setPredicting(false); }
  };

  if (!model) return <div className="p-8" role={error ? "alert" : "status"}>{error || healthError ? messageText(error || healthError, t) : t("loading")}</div>;

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
            onKeyDown={(e) => { if (e.key === "Enter") handleRenameName(); if (e.key === "Escape") setEditingName(false); }}
            autoFocus
          />
          <button onClick={handleRenameName} className="btn btn-primary btn-sm">{t("save")}</button>
          <button onClick={() => setEditingName(false)} className="btn btn-ghost btn-sm">{t("cancel")}</button>
        </div>
      ) : (
        <h1
          className="text-2xl font-bold mb-6 cursor-pointer hover:underline"
          onClick={() => { setNameDraft(model.model_name || t("modelNumber", { id: model.id })); setEditingName(true); }}
          title={t("renameHint")}
        >
          {model.model_name || t("modelDetailTitle", { model_id: model.id, dataset_name: model.dataset_name })}
        </h1>
      )}

      {error && <div className="alert alert-error mb-4">{messageText(error, t)}</div>}
      {model.pending_cleanup && <Link className="btn mb-4" to={`/operations/delete/${model.pending_cleanup}`}>{t("openCleanup")}</Link>}

      {/* Model info card */}
      <div className="card bg-base-100 shadow-lg mb-6">
        <div className="card-body">
          <fieldset className="fieldset">
            <legend className="fieldset-legend">{t("labels")}</legend>
            {editingLabels ? (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  className="input input-bordered w-full"
                  value={labelsDraft}
                  onChange={(e) => setLabelsDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") handleRenameLabels(); if (e.key === "Escape") setEditingLabels(false); }}
                  autoFocus
                />
                <button onClick={handleRenameLabels} className="btn btn-primary btn-sm">{t("save")}</button>
                <button onClick={() => setEditingLabels(false)} className="btn btn-ghost btn-sm">{t("cancel")}</button>
              </div>
            ) : (
              <input
                type="text"
                className="input input-bordered w-full cursor-pointer hover:border-primary"
                value={model.labels.join(", ")}
                readOnly
                onClick={() => { setLabelsDraft(model.labels.join(", ")); setEditingLabels(true); }}
                title={t("editHint")}
              />
            )}
          </fieldset>

          <fieldset className="fieldset">
            <legend className="fieldset-legend">{t("preprocessingFunction")}</legend>
            <input
              type="text"
              className="input input-bordered w-full"
              value={model.a_preprocess_fun}
              readOnly
            />
          </fieldset>

          <p className="font-semibold mt-2">
            {t("verifiedModel", { status: t(model.trained ? "verified" : model.artifact_status === "UNVERIFIED" ? "notChecked" : "unavailable") })}
          </p>

          <div role="status">
            <p>{t("servingStatus", { status: statusText(healthError ? "UNAVAILABLE" : model.serving.status, t) })}</p>
            <p className="text-sm">{messageText(healthError || model.serving.error?.message || "", t, model.serving.error?.code)}</p>
            {model.serving.training_run_id && <p className="text-sm break-all">{t("loadedRun", { id: model.serving.training_run_id })}</p>}
            {model.serving.class_schema_version === 1 && <p>{t("legacyClassNote")}</p>}
            {model.serving.labels.length > 0 && <p>{t("loadedClasses", { labels: (model.serving.class_schema_version === 1 ? "OTHER, " : "") + model.serving.labels.join(", ") })}</p>}
          </div>
          <p className="text-sm">{t("classEditsNote")}</p>
          {!model.labels_valid && <p role="alert">{t("correctClasses")}</p>}
          {model.last_training_run && <p>{t("lastTraining", { status: statusText(model.last_training_run.status, t) })}
            {model.last_training_run.error && <span className="block text-error">{messageText(model.last_training_run.error.message, t, model.last_training_run.error.code)}</span>}
          </p>}
          <div className="card-actions justify-end mt-4">
            <button onClick={handleTrain} className="btn btn-primary" disabled={submitting}>
              {t(submitting ? "submitting" : model.last_training_run && !model.last_training_run.is_finished ? "viewActiveTraining" : "trainModel")}
            </button>
            <button onClick={handleServe} className="btn" disabled={!model.trained || submitting || ["STARTING", "READY", "UNAVAILABLE", "STOPPING"].includes(model.serving.status)}>
              {t("serveModel")}
            </button>
            {model.serving.id && model.serving.status !== "STOPPED" && <button onClick={handleStop} className="btn" disabled={submitting || model.serving.status === "STOPPING"}>{t("stopServing")}</button>}
            <button className="btn btn-error" onClick={() => navigate(`/cleanup/models/${modelId}/model`)}>{t("deleteModel")}</button>
            <button onClick={handleDelete} className="btn">
              {t("deleteModelFiles")}
            </button>
          </div>
        </div>
      </div>

      <section className="card bg-base-100 shadow-lg mb-6" aria-label={t("history")}>
        <div className="card-body">
          <h2 className="card-title">{t("history")}</h2>
          {history.length === 0 ? <p>{t("noTrainingRuns")}</p> : <ul className="space-y-3">
            {history.map(run => <li key={run.id}>
              <button className="link" onClick={() => navigate(`/models/${modelId}/train/${run.id}`)}>{statusText(run.status, t)} · {new Date(run.created_at).toLocaleString(i18n.resolvedLanguage === "ru" ? "ru-RU" : "en-US")}</button>
              <p>{t("classes", { labels: run.labels.join(", ") })}{run.published ? ` · ${t("published")}` : ""}{run.served ? ` · ${t("selectedForServing")}` : ""}</p>
              {run.quality ? <div className="text-sm">
                <p>{t("validationMetrics", { count: run.quality.samples,
                  accuracy: (run.quality.accuracy * 100).toFixed(1), f1: run.quality.macro_f1.toFixed(3),
                  baseline: (run.quality.majority_baseline * 100).toFixed(1), steps: run.quality.training_steps })}</p>
                <p>{t("validationScope")}</p>
                {run.quality.warnings.map(warning => <p className="text-warning" key={warning}>{t(`quality_${warning}`)}</p>)}
              </div> : <p className="text-sm">{t(run.is_finished ? "qualityUnknown" : "qualityPending")}</p>}
              {run.error && <p className="text-error">{messageText(run.error.message, t, run.error.code)}</p>}
            </li>)}
          </ul>}
        </div>
      </section>

      {/* Predict card */}
      <div className="card bg-base-100 shadow-lg">
        <div className="card-body">
          <h2 className="card-title">{t("textInput")}</h2>
          <form onSubmit={handlePredict}>
            <textarea
              rows={4}
              maxLength={20000}
              className="textarea textarea-bordered w-full"
              placeholder={t("enterTextHere")}
              value={textInput}
              onChange={(e) => changeText(e.target.value)}
              aria-label={t("textInput")}
            />
            <div className="card-actions justify-end mt-4">
              <button type="submit" className="btn btn-primary" disabled={!model.served || !!healthError || predicting || !textInput.trim()}>
                {t(predicting ? "predicting" : "predictModel")}
              </button>
            </div>
          </form>
          {predictionError && <div role="alert" className="alert alert-error mt-4">{messageText(predictionError, t)}</div>}
          {prediction !== null && prediction.text === textInput && prediction.context === predictionContext && (
            <div role="status" className="alert alert-success mt-4">
              {t("predictionResult", { predicted: prediction.label })}
            </div>
          )}
        </div>
      </div>
      </div>
    </div>
  );
}

export default ModelDetailPage;
