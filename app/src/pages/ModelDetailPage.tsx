import { useParams, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { API } from "../api";

interface Model {
  id: number;
  labels: string;
  a_preprocess_fun: string;
  dataset_name: string;
  trained: boolean;
  served: boolean;
}

function ModelDetailPage() {
  const { modelId } = useParams<{ modelId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [model, setModel] = useState<Model | null>(null);
  const [textInput, setTextInput] = useState("");
  const [prediction, setPrediction] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!modelId) return;
    fetch(`${API}/api/models/${modelId}/`)
      .then(res => {
        if (!res.ok) throw new Error("Failed to load model");
        return res.json();
      })
      .then(data => setModel(data))
      .catch(err => setError(err.message));
  }, [modelId]);

  const handleTrain = async () => {
    try {
      const res = await fetch(`${API}/api/models/${modelId}/train/`, { method: "POST" });
      if (!res.ok) throw new Error("Failed to start training");
      const data = await res.json();
      navigate(`/models/${modelId}/train/${data.result_id}`);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleServe = async () => {
    try {
      const res = await fetch(`${API}/api/models/${modelId}/serve/`, { method: "POST" });
      if (!res.ok) throw new Error("Failed to start serving");
      const data = await res.json();
      navigate(`/models/${modelId}/serve/${data.result_id}`);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm("Delete this model's K8s resources?")) return;
    try {
      const res = await fetch(`${API}/api/models/${modelId}/delete_model/`, { method: "POST" });
      if (!res.ok) throw new Error("Failed to start deletion");
      const data = await res.json();
      navigate(`/models/${modelId}/delete/${data.result_id}`);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handlePredict = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!modelId || !model?.served) return;
    setError("");
    try {
      const response = await fetch(`${API}/api/models/${modelId}/predict/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text_input: textInput }),
      });
      if (!response.ok) throw new Error("Prediction failed");
      const data = await response.json();
      setPrediction(data.predicted_class);
    } catch (err: any) {
      setError(err.message);
    }
  };

  if (!model) return <div className="p-8">Loading...</div>;

  return (
    <div className="min-h-screen bg-base-200 p-8">
      <div className="max-w-3xl mx-auto">
      <button onClick={() => navigate("/")} className="btn btn-sm btn-outline mb-6">
        {t("home")}
      </button>

      <h1 className="text-2xl font-bold mb-6">
        {t("modelDetailTitle", { model_id: model.id, dataset_name: model.dataset_name })}
      </h1>

      {error && <div className="alert alert-error mb-4">{error}</div>}

      {/* Model info card */}
      <div className="card bg-base-100 shadow-lg mb-6">
        <div className="card-body">
          <fieldset className="fieldset">
            <legend className="fieldset-legend">{t("labels")}</legend>
            <input
              type="text"
              className="input input-bordered w-full"
              value={model.labels}
              readOnly
            />
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
            Trained: {model.trained ? "Yes" : "No"} &nbsp;&nbsp; Served: {model.served ? "Yes" : "No"}
          </p>

          <div className="card-actions justify-end mt-4">
            <button onClick={handleTrain} className="btn btn-primary">
              {t("trainModel")}
            </button>
            <button onClick={handleServe} className="btn">
              {t("serveModel")}
            </button>
            <button onClick={handleDelete} className="btn">
              {t("deleteModel")}
            </button>
          </div>
        </div>
      </div>

      {/* Predict card */}
      <div className="card bg-base-100 shadow-lg">
        <div className="card-body">
          <h2 className="card-title">{t("textInput")}</h2>
          <form onSubmit={handlePredict}>
            <textarea
              rows={4}
              className="textarea textarea-bordered w-full"
              placeholder={t("enterTextHere")}
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
            />
            <div className="card-actions justify-end mt-4">
              <button type="submit" className="btn btn-primary" disabled={!model.served}>
                {t("predictModel")}
              </button>
            </div>
          </form>
          {prediction && (
            <div className="alert alert-success mt-4">
              {t("predictionResult", { predicted: prediction })}
            </div>
          )}
        </div>
      </div>
      </div>
    </div>
  );
}

export default ModelDetailPage;
