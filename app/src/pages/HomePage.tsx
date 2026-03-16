import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { createDataset, fetchIndex, type Model, type Dataset } from "../api";

export default function HomePage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();

  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [latestDataset, setLatestDataset] = useState<{
    name: string;
    id: number;
  } | null>(null);
  const [loading, setLoading] = useState(true);

  const [formData, setFormData] = useState({
    dataset_name: "",
    data_table_name: "",
    id_field: "",
    image: "",
    workingDir: "",
    pipeline: "",
    recipe_options: "",
  });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchIndex()
      .then((data) => {
        setDatasets(data.datasets);
        setModels(data.models);
        setLatestDataset(data.latest_dataset);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleCreateDataset = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const datasetId = await createDataset(formData);
      navigate(`/datasets/${datasetId}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-base-200">
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Language switch */}
        <div className="flex gap-2 mb-6">
          <button
            className={`btn btn-sm ${i18n.language === "en" ? "btn-primary" : "btn-outline"}`}
            onClick={() => i18n.changeLanguage("en")}
          >
            EN
          </button>
          <button
            className={`btn btn-sm ${i18n.language === "ru" ? "btn-primary" : "btn-outline"}`}
            onClick={() => i18n.changeLanguage("ru")}
          >
            RU
          </button>
        </div>

        <h1 className="text-3xl font-bold uppercase mb-6">{t("title")}</h1>

        {/* Prodigy status */}
        {latestDataset ? (
          <div className="alert alert-success mb-6">
            Prodigy running for dataset{" "}
            <Link
              to={`/datasets/${latestDataset.id}`}
              className="underline font-semibold"
            >
              {latestDataset.name}
            </Link>
          </div>
        ) : (
          <div className="alert alert-warning mb-6">
            {t("prodigyNotRunning")}
          </div>
        )}

        {error && <div className="alert alert-warning mb-6">{error}</div>}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
          {/* MODELS LIST */}
          <div className="lg:col-span-1">
            <h2 className="text-2xl font-semibold mb-4">{t("yourModels")}</h2>
            {loading ? (
              <p className="text-gray-500">Loading...</p>
            ) : models.length > 0 ? (
              <ul className="menu bg-base-100 rounded-box p-4 shadow">
                {models.map((model) => (
                  <li key={model.id}>
                    <Link
                      to={`/models/${model.id}`}
                      state={{ trained: model.trained }}
                      className="hover:bg-base-200 p-3 rounded flex flex-col gap-1 text-left w-full"
                    >
                      <span className="font-semibold truncate">
                        {model.dataset_name}
                      </span>
                      <span className="text-xs text-gray-500 truncate">
                        {model.labels}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-gray-500">{t("noModels")}</p>
            )}

            {/* DATASETS LIST */}
            <h2 className="text-2xl font-semibold mb-4 mt-6">Datasets</h2>
            {loading ? (
              <p className="text-gray-500">Loading...</p>
            ) : datasets.length > 0 ? (
              <ul className="menu bg-base-100 rounded-box p-4 shadow">
                {datasets.map((ds) => (
                  <li key={ds.id}>
                    <Link
                      to={`/datasets/${ds.id}`}
                      className="hover:bg-base-200 p-3 rounded text-left w-full"
                    >
                      <span className="font-semibold truncate">
                        {ds.dataset_name}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-gray-500">No datasets found.</p>
            )}
          </div>

          {/* CREATE DATASET */}
          <div className="lg:col-span-2">
            <div className="card bg-base-100 shadow-lg rounded-xl p-8">
              <form onSubmit={handleCreateDataset} className="grid gap-4">
                <label className="form-control w-full">
                  <span className="label-text font-medium">{t("name")}</span>
                  <input
                    name="dataset_name"
                    className="input input-bordered w-full"
                    value={formData.dataset_name}
                    onChange={handleInputChange}
                  />
                </label>
                <label className="form-control w-full">
                  <span className="label-text font-medium">
                    {t("dataTable")}
                  </span>
                  <input
                    name="data_table_name"
                    className="input input-bordered w-full"
                    value={formData.data_table_name}
                    onChange={handleInputChange}
                  />
                </label>
                <label className="form-control w-full">
                  <span className="label-text font-medium">
                    {t("idField")}
                  </span>
                  <input
                    name="id_field"
                    className="input input-bordered w-full"
                    value={formData.id_field}
                    onChange={handleInputChange}
                  />
                </label>
                <label className="form-control w-full">
                  <span className="label-text font-medium">{t("image")}</span>
                  <input
                    name="image"
                    className="input input-bordered w-full"
                    value={formData.image}
                    onChange={handleInputChange}
                  />
                </label>
                <label className="form-control w-full">
                  <span className="label-text font-medium">
                    {t("workingDir")}
                  </span>
                  <input
                    name="workingDir"
                    className="input input-bordered w-full"
                    value={formData.workingDir}
                    onChange={handleInputChange}
                  />
                </label>
                <label className="form-control w-full">
                  <span className="label-text font-medium">
                    {t("pipeline")}
                  </span>
                  <input
                    name="pipeline"
                    className="input input-bordered w-full"
                    value={formData.pipeline}
                    onChange={handleInputChange}
                  />
                </label>
                <label className="form-control w-full">
                  <span className="label-text font-medium">
                    {t("recipeOptions")}
                  </span>
                  <input
                    name="recipe_options"
                    className="input input-bordered w-full"
                    value={formData.recipe_options}
                    onChange={handleInputChange}
                  />
                </label>
                <button
                  type="submit"
                  className="btn btn-primary mt-2 w-full"
                  disabled={submitting}
                >
                  {submitting ? "Creating..." : t("create")}
                </button>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
