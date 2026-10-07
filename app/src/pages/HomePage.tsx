import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { API } from "../api";

interface Dataset {
  id: number;
  dataset_name: string;
  image: string;
  workingDir: string;
  pipeline: string;
  recipe_options: string;
  data_table_name: string;
  id_field: string;
  labelled: boolean;
}

interface Model {
  id: number;
  on_dataset: number;
  dataset_name: string;
  labels: string;
  a_preprocess_fun: string;
  trained: boolean;
  served: boolean;
}

export default function HomePage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();

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

  const load = async () => {
    try {
      const [dRes, mRes] = await Promise.all([
        fetch(`${API}/api/datasets/`),
        fetch(`${API}/api/models/`),
      ]);
      if (!dRes.ok || !mRes.ok) throw new Error("Failed to load data");
      setDatasets(await dRes.json());
      setModels(await mRes.json());
    } catch (err: any) {
      setError(err.message);
    }
  };

  useEffect(() => {
    load();
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
      if (!res.ok) throw new Error("Failed to create dataset");
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
    } catch (err: any) {
      setError(err.message);
    }
  };

  const formFields = [
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
      {/* Navbar */}
      <div className="navbar bg-base-100 shadow-sm">
        <div className="flex-1">
          <span className="text-xl font-bold px-4">Kedrogy</span>
        </div>
        <div className="flex-none gap-2 pr-4">
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
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8">
        <h1 className="text-3xl font-bold uppercase mb-6">{t("title")}</h1>

        {error && <div className="alert alert-error mb-6">{error}</div>}

        {/* Prodigy status badge */}
        {datasets.length > 0 && (() => {
          const latest = datasets[datasets.length - 1];
          return (
            <div className="mb-6">
              <span
                className="badge badge-primary badge-lg p-4 cursor-pointer"
                onClick={() => navigate(`/datasets/${latest.id}`)}
              >
                {t("prodigyRunning", { dataset: latest.dataset_name })}
              </span>
            </div>
          );
        })()}

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
                        <th>Trained</th>
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
                          <td>{model.labels}</td>
                          <td>{model.trained ? "Yes" : "No"}</td>
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
              <h2 className="text-2xl font-semibold mb-4">Datasets</h2>
              {datasets.length > 0 ? (
                <div className="overflow-x-auto bg-base-100 rounded-xl shadow">
                  <table className="table table-zebra">
                    <thead>
                      <tr>
                        <th>{t("name")}</th>
                        <th>{t("dataTable")}</th>
                        <th>Labelled</th>
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
                          <td>{ds.labelled ? "Yes" : "No"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-gray-500">No datasets yet.</p>
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
                        value={(formData as any)[field.name]}
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
