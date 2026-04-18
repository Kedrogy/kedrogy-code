import { useParams, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { API } from "../api";

function DatasetDetailPage() {
  const { datasetId } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [dataset, setDataset] = useState<any>(null);
  const [error, setError] = useState("");
  const [labels, setLabels] = useState("");
  const [preprocessFun, setPreprocessFun] = useState("");

  useEffect(() => {
    fetch(`${API}/api/datasets/${datasetId}/`)
      .then(res => res.json())
      .then(data => setDataset(data))
      .catch(err => setError(err.message));
  }, [datasetId]);

  const handleDelete = async () => {
    if (!window.confirm("Delete this dataset?")) return;
    try {
      const res = await fetch(`${API}/api/datasets/${datasetId}/`, { method: "DELETE" });
      if (!res.ok) throw new Error("Failed to delete");
      navigate("/");
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleLabel = async () => {
    try {
      const res = await fetch(`${API}/api/datasets/${datasetId}/label/`, { method: "POST" });
      if (!res.ok) throw new Error("Failed to start labeling");
      const data = await res.json();
      navigate(`/datasets/task/${data.result_id}`);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleCreateModel = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API}/api/models/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          on_dataset: Number(datasetId),
          labels,
          a_preprocess_fun: preprocessFun,
        }),
      });
      if (!res.ok) throw new Error("Failed to create model");
      const data = await res.json();
      navigate(`/models/${data.id}`);
    } catch (err: any) {
      setError(err.message);
    }
  };

  if (!dataset) return <div className="p-8">Loading...</div>;

  return (
    <div className="min-h-screen bg-base-200 p-8">
      <div className="max-w-3xl mx-auto">
      <button onClick={() => navigate("/")} className="btn btn-sm btn-outline mb-6">
        {t("home")}
      </button>

      <h1 className="text-2xl font-bold mb-6">
        {t("datasetDetailTitle", { name: dataset.dataset_name })}
      </h1>

      {error && <div className="alert alert-error mb-4">{error}</div>}

      {/* Dataset details card */}
      <div className="card bg-base-100 shadow-lg mb-6">
        <div className="card-body">
          <table className="table">
            <tbody>
              <tr><td>{t("dataTable")}</td><td className="text-right">{dataset.data_table_name}</td></tr>
              <tr><td>{t("idField")}</td><td className="text-right">{dataset.id_field}</td></tr>
              <tr><td>{t("image")}</td><td className="text-right">{dataset.image}</td></tr>
              <tr><td>{t("workingDir")}</td><td className="text-right">{dataset.workingDir}</td></tr>
              <tr><td>pipeline</td><td className="text-right">{dataset.pipeline}</td></tr>
              <tr><td>recipe_options</td><td className="text-right">{dataset.recipe_options}</td></tr>
              <tr><td>Labelled</td><td className="text-right font-semibold">{dataset.labelled ? "Yes" : "No"}</td></tr>
            </tbody>
          </table>
          <div className="card-actions mt-4">
            <button onClick={handleDelete} className="btn btn-error btn-sm">
              {t("delete")}
            </button>
            <button onClick={handleLabel} className="btn btn-primary btn-sm">
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
                placeholder="e.g. POS, NEG"
                value={labels}
                onChange={(e) => setLabels(e.target.value)}
                required
              />
            </fieldset>
            <fieldset className="fieldset">
              <legend className="fieldset-legend">{t("preprocessingFunction")}</legend>
              <input
                className="input input-bordered w-full"
                placeholder="e.g. preprocessing_fun"
                value={preprocessFun}
                onChange={(e) => setPreprocessFun(e.target.value)}
              />
            </fieldset>
            <div className="card-actions justify-end mt-4">
              <button type="submit" className="btn btn-primary" disabled={!dataset.labelled}>
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
