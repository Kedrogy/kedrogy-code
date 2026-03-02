import { useParams, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

interface Model {
  id: number;
  labels: string;
  a_preprocess_fun: string;
  dataset_name: string;
}

function ModelDetailPage() {
  const { modelId } = useParams<{ modelId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [model, setModel] = useState<Model | null>(null);
  const [textInput, setTextInput] = useState("");
  const [prediction, setPrediction] = useState<string | null>(null);

  useEffect(() => {
    if (!modelId) return;

    fetch(`/api/models/${modelId}`)
      .then(res => {
        if (!res.ok) throw new Error("Failed to load model");
        return res.json();
      })
      .then(data => setModel(data))
      .catch(err => console.error(err));
  }, [modelId]);

  const handlePredict = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!modelId) return;

    try {
      const response = await fetch(`/api/models/${modelId}/predict`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ text_input: textInput }),
      });

      if (!response.ok) throw new Error("Prediction failed");

      const data = await response.json();
      setPrediction(data.predicted_class);
    } catch (err) {
      console.error(err);
    }
  };

  if (!model) return <div className="p-8">Loading...</div>;

  return (
    <div className="min-h-screen bg-base-200 font-sans p-8">
      <button
        onClick={() => navigate("/")}
        className="btn btn-sm btn-outline mb-6"
      >
        {t("home")}
      </button>

      <h1 className="text-2xl font-bold mb-6">
        {t("modelDetailTitle", {
          model_id: model.id,
          dataset_name: model.dataset_name,
        })}
      </h1>

      <div className="card bg-base-100 shadow-lg p-6 mb-6">
        <div className="mb-4">
          <h2 className="font-semibold mb-1">{t("labels")}</h2>
          <input
            type="text"
            className="input input-bordered w-full"
            value={model.labels}
            readOnly
          />
        </div>

        <div className="mb-4">
          <h2 className="font-semibold mb-1">
            {t("preprocessingFunction")}
          </h2>
          <input
            type="text"
            className="input input-bordered w-full"
            value={model.a_preprocess_fun}
            readOnly
          />
        </div>

        <div className="mt-4 flex gap-2">
          <button
            onClick={() => navigate(`/models/${modelId}/delete`)}
            className="btn btn-error"
          >
            {t("deleteModel")}
          </button>

          <button
            onClick={() => navigate(`/models/${modelId}/serve`)}
            className="btn btn-success"
          >
            {t("serveModel")}
          </button>
        </div>
      </div>

      <div className="card bg-base-100 shadow-lg p-6">
        <h2 className="text-xl font-semibold mb-4">
          {t("textInput")}
        </h2>

        <form onSubmit={handlePredict}>
          <textarea
            rows={4}
            className="textarea textarea-bordered w-full mb-4"
            placeholder={t("enterTextHere")}
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
          />

          <button type="submit" className="btn btn-primary">
            {t("predictModel")}
          </button>
        </form>

        {prediction && (
          <div className="alert alert-success mt-4">
            {t("predictionResult", { predicted: prediction })}
          </div>
        )}
      </div>
    </div>
  );
}

export default ModelDetailPage;