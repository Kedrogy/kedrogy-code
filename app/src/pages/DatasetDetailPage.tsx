import { useParams, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  fetchDataset,
  createModel,
  labelDataset,
  deleteDataset,
  type Dataset,
} from "../api";

export default function DatasetDetailPage() {
  const { datasetId } = useParams<{ datasetId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [error, setError] = useState("");

  // Create-model form
  const [labels, setLabels] = useState("");
  const [preprocessFun, setPreprocessFun] = useState("");
  const [creatingModel, setCreatingModel] = useState(false);

  // Label / delete
  const [labeling, setLabeling] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!datasetId) return;
    fetchDataset(datasetId)
      .then(setDataset)
      .catch((err) =>
        setError(err instanceof Error ? err.message : String(err))
      );
  }, [datasetId]);

  const handleLabel = async () => {
    if (!datasetId) return;
    setLabeling(true);
    setError("");
    try {
      const resultId = await labelDataset(datasetId);
      navigate(`/datasets/task/${resultId}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setLabeling(false);
    }
  };

  const handleDelete = async () => {
    if (!datasetId) return;
    setDeleting(true);
    setError("");
    try {
      await deleteDataset(datasetId);
      navigate("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setDeleting(false);
    }
  };

  const handleCreateModel = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!datasetId) return;
    setCreatingModel(true);
    setError("");
    try {
      const modelId = await createModel(datasetId, labels, preprocessFun);
      navigate(`/models/${modelId}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreatingModel(false);
    }
  };

  if (error && !dataset)
    return <div className="p-8 text-red-500">{error}</div>;
  if (!dataset) return <div className="p-8">Loading...</div>;

  return (
    <div className="min-h-screen bg-base-200 font-sans p-8">
      <button
        onClick={() => navigate("/")}
        className="btn btn-sm btn-outline mb-6"
      >
        {t("home")}
      </button>

      <h1 className="text-2xl font-bold mb-6">{dataset.dataset_name}</h1>

      {error && <div className="alert alert-warning mb-4">{error}</div>}

      {/* Dataset details */}
      <div className="card bg-base-100 shadow-md p-6 mb-6 max-w-3xl">
        <div className="grid gap-4">
          <div className="flex justify-between">
            <span>{t("dataTable")}</span>
            <span>{dataset.data_table_name}</span>
          </div>
          <div className="flex justify-between">
            <span>{t("idField")}</span>
            <span>{dataset.id_field}</span>
          </div>
          <div className="flex justify-between">
            <span>{t("image")}</span>
            <span>{dataset.image}</span>
          </div>
        </div>
      </div>

      {/* Label & Delete actions */}
      <div className="flex gap-2 mb-6">
        <button
          className="btn btn-primary btn-sm"
          onClick={handleLabel}
          disabled={labeling}
        >
          {labeling ? "Starting..." : t("labelDataset")}
        </button>
        <button
          className="btn btn-error btn-sm"
          onClick={handleDelete}
          disabled={deleting}
        >
          {deleting ? "Deleting..." : t("delete")}
        </button>
      </div>

      {/* Create model on this dataset */}
      <div className="card bg-base-100 shadow-md p-6 max-w-3xl">
        <h2 className="text-xl font-semibold mb-4">{t("newModel")}</h2>
        <form onSubmit={handleCreateModel} className="grid gap-4">
          <input
            placeholder="Labels (comma-separated, e.g. POS,NEG)"
            className="input input-bordered w-full"
            value={labels}
            onChange={(e) => setLabels(e.target.value)}
          />
          <input
            placeholder="Preprocessing function"
            className="input input-bordered w-full"
            value={preprocessFun}
            onChange={(e) => setPreprocessFun(e.target.value)}
          />
          <button
            type="submit"
            className="btn btn-primary"
            disabled={creatingModel}
          >
            {creatingModel ? "Creating..." : t("create")}
          </button>
        </form>
      </div>
    </div>
  );
}
