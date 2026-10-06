import { messageText, statusText } from "../i18n/messages";
import { parseAnnotationSession, type AnnotationSession } from "../api/operations";
import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { API } from "../api";

import { parseModel, parseDataset, type Dataset, type Model } from "../api/models";
import { responseError } from "../api/tasks";

export default function HomePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [annotation, setAnnotation] = useState<AnnotationSession | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [formData, setFormData] = useState({
    dataset_name: "",
    data_table_name: "",
    id_field: "",
    image: "",
    workingDir: "",
    pipeline: "",
    recipe_options: "",
  });

  const load = async (signal = AbortSignal.timeout(10000)) => {
    try {
      const [dRes, mRes, aRes] = await Promise.all([
        fetch(`${API}/api/datasets/`, { signal }),
        fetch(`${API}/api/models/`, { signal }),
        fetch(`${API}/api/datasets/active_annotation/`, { signal }),
      ]);
      if (!dRes.ok || !mRes.ok || !aRes.ok) throw new Error("Failed to load data");
      const datasets: unknown = await dRes.json();
      const models: unknown = await mRes.json();
      if (!Array.isArray(datasets) || !Array.isArray(models)) throw new Error("The list response is invalid.");
      const active = parseAnnotationSession(await aRes.json());
      if (signal.aborted) return;
      setAnnotation(active);
      setDatasets(datasets.map(parseDataset));
      setModels(models.map(parseModel));
    } catch (err: unknown) {
      if (!signal.aborted) setError(err instanceof Error ? err.message : "The request failed.");
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      await load(AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]));
      if (!controller.signal.aborted) timer = setTimeout(() => { void refresh(); }, 10000);
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, []);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleCreateDataset = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const res = await fetch(`${API}/api/datasets/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });
      if (!res.ok) throw new Error(await responseError(res));
      setFormData({
        dataset_name: "",
        data_table_name: "",
        id_field: "",
        image: "",
        workingDir: "",
        pipeline: "",
        recipe_options: "",
      });
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "The request failed.");
    }
  };

  const formFields: { name: keyof typeof formData; label: string }[] = [
    { name: "dataset_name", label: t("name") },
    { name: "data_table_name", label: t("dataTable") },
    { name: "id_field", label: t("idField") },
    { name: "image", label: t("image") },
    { name: "workingDir", label: t("workingDir") },
    { name: "pipeline", label: t("pipeline") },
    { name: "recipe_options", label: t("recipeOptions") },
  ];

  return (
    <div className="min-h-screen bg-base-200">
      <div className="max-w-7xl mx-auto px-6 py-8">
        <h1 className="text-3xl font-bold uppercase mb-6">{t("title")}</h1>

        {error && <div className="alert alert-error mb-6">{messageText(error, t)}</div>}

        <div className="mb-6 space-x-4" aria-live="polite">
          <span>{t("annotationSession", { status: annotation ? statusText(annotation.status, t) : t("loading") })}</span>
          {annotation?.dataset_id && <Link to={`/datasets/${annotation.dataset_id}`}>{t("datasetNumber", { id: annotation.dataset_id })}</Link>}
          {annotation?.url && <a href={annotation.url} target="_blank" rel="noreferrer">{t("openAnnotationSession")}</a>}
          <Link to="/retained-annotations">{t("retainedAnnotations")}</Link>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">

          {/* LEFT: Tables */}
          <div className="lg:col-span-1 space-y-6">
            {/* Models table */}
            <div>
              <h2 className="text-2xl font-semibold mb-4">{t("yourModels")}</h2>
              {models.length > 0 ? (
                <div className="overflow-x-auto bg-base-100 rounded-xl shadow">
                  <table className="table table-zebra">
                    <thead>
                      <tr>
                        <th>{t("name")}</th>
                        <th>{t("labels")}</th>
                        <th>{t("trained")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {models.map((model) => (
                        <tr
                          key={model.id}
                          className="cursor-pointer hover"
                          onClick={() => navigate(`/models/${model.id}`)}
                        >
                          <td className="font-semibold">{model.dataset_name}</td>
                          <td>{model.labels.join(", ")}</td>
                          <td>{t(model.trained ? "verified" : model.artifact_status === "UNVERIFIED" ? "notChecked" : "unavailable")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-gray-500">{t("noModels")}</p>
              )}
            </div>

            {/* Datasets table */}
            <div>
              <h2 className="text-2xl font-semibold mb-4">{t("datasets")}</h2>
              {datasets.length > 0 ? (
                <div className="overflow-x-auto bg-base-100 rounded-xl shadow">
                  <table className="table table-zebra">
                    <thead>
                      <tr>
                        <th>{t("name")}</th>
                        <th>{t("dataTable")}</th>
                        <th>{t("annotationData")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {datasets.map((ds) => (
                        <tr
                          key={ds.id}
                          className="cursor-pointer hover"
                          onClick={() => navigate(`/datasets/${ds.id}`)}
                        >
                          <td className="font-semibold">{ds.dataset_name}</td>
                          <td>{ds.data_table_name}</td>
                          <td>{statusText(ds.annotation_data.status, t)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-gray-500">{t("noDatasets")}</p>
              )}
            </div>
          </div>

          {/* RIGHT: Create Dataset Card */}
          <div className="lg:col-span-2">
            <div className="card bg-base-100 shadow-lg">
              <div className="card-body">
                <h2 className="card-title">{t("create")}</h2>
                <form onSubmit={handleCreateDataset} className="space-y-4">
                  {formFields.map((field) => (
                    <fieldset key={field.name} className="fieldset">
                      <legend className="fieldset-legend">{field.label}</legend>
                      <input
                        name={field.name}
                        className="input input-bordered w-full"
                        value={formData[field.name]}
                        onChange={handleInputChange}
                      />
                    </fieldset>
                  ))}
                  <div className="card-actions justify-end mt-4">
                    <button type="submit" className="btn btn-primary">
                      {t("create")}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
