import { useParams, useNavigate, useLocation } from "react-router-dom";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { startTraining } from "../api";

export default function ModelDetailPage() {
  const { modelId } = useParams<{ modelId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();

  const [error, setError] = useState("");
  const [isStarting, setIsStarting] = useState(false);

  // Training status is passed via React Router state from TrainModelPage
  const trained =
    (location.state as { trained?: boolean })?.trained ?? false;

  const handleTrain = async () => {
    if (!modelId) return;
    setIsStarting(true);
    setError("");
    try {
      const resultId = await startTraining(modelId);
      navigate(`/models/${modelId}/train/${resultId}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setIsStarting(false);
    }
  };

  return (
    <div className="min-h-screen bg-base-200 font-sans p-8">
      <button
        onClick={() => navigate("/")}
        className="btn btn-sm btn-outline mb-6"
      >
        {t("home")}
      </button>

      <h1 className="text-2xl font-bold mb-6">Model #{modelId}</h1>

      {error && <div className="alert alert-warning mb-4">{error}</div>}

      <div className="card bg-base-100 shadow-lg p-6">
        <div className="flex gap-2">
          <button
            className="btn btn-primary"
            onClick={handleTrain}
            disabled={isStarting}
          >
            {isStarting ? "Starting..." : "Train Model"}
          </button>

          <button
            className="btn btn-success"
            onClick={() => navigate(`/models/${modelId}/serve`)}
            disabled={!trained}
          >
            Serve Model
          </button>
        </div>

        {!trained && (
          <p className="text-sm text-gray-500 mt-2">
            Train the model first to enable serving.
          </p>
        )}
      </div>
    </div>
  );
}
