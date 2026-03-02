import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";

interface Model {
  id: number;
  dataset: string;
  labels: string;
}

export default function HomePage() {
  const { t, i18n } = useTranslation();

  const [mode, setMode] = useState<"home" | "createDataset" | "modelDetail" | "trainModel" | "serveModel">("home");
  const [selectedModel, setSelectedModel] = useState<Model | null>(null);

  const [models] = useState<Model[]>([
    { id: 1, dataset: "test_dataset", labels: "POS, NEG" },
    { id: 2, dataset: "test222", labels: "PS, NG" },
  ]);

  const [formData, setFormData] = useState({
    name: "",
    dataTable: "",
    idField: "",
    image: "",
    workingDir: "",
    pipeline: "",
    recipeOptions: "",
  });

  const [trainLogs, setTrainLogs] = useState("");
  const [serveLogs, setServeLogs] = useState("");
  const [trainingFinished, setTrainingFinished] = useState(false);

  const isProdigyRunning = true;

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleCreateDataset = (e: React.FormEvent) => {
    e.preventDefault();
    console.log("Creating dataset:", formData);
    setFormData({
      name: "",
      dataTable: "",
      idField: "",
      image: "",
      workingDir: "",
      pipeline: "",
      recipeOptions: "",
    });
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

        {isProdigyRunning ? (
          <div className="alert alert-success mb-6">
            {t("prodigyRunning", { dataset: "test_dataset" })}
          </div>
        ) : (
          <div className="alert alert-warning mb-6">
            {t("prodigyNotRunning")}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">

          {/* MODELS LIST */}
          <div className="lg:col-span-1">
            <h2 className="text-2xl font-semibold mb-4">{t("yourModels")}</h2>
            {models.length > 0 ? (
              <ul className="menu bg-base-100 rounded-box p-4 shadow">
                {models.map((model) => (
                  <li key={model.id}>
                    <button
                      className="hover:bg-base-200 p-3 rounded flex flex-col gap-1 text-left w-full"
                      onClick={() => {
                        setSelectedModel(model);
                        setMode("modelDetail");
                        setTrainingFinished(false);
                        setTrainLogs("");
                        setServeLogs("");
                      }}
                    >
                      <span className="font-semibold truncate">{model.dataset}</span>
                      <span className="text-xs text-gray-500 truncate">{model.labels}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-gray-500">{t("noModels")}</p>
            )}
          </div>

          {/* CONTENT */}
          <div className="lg:col-span-2">

            {/* CREATE DATASET */}
            {(mode === "home" || mode === "createDataset") && (
              <div className="card bg-base-100 shadow-lg rounded-xl p-8">
                <form onSubmit={handleCreateDataset} className="grid gap-4">
                  {Object.keys(formData).map((key) => (
                    <input
                      key={key}
                      name={key}
                      placeholder={t(key as keyof typeof formData)}
                      className="input input-bordered w-full"
                      value={(formData as any)[key]}
                      onChange={handleInputChange}
                    />
                  ))}
                  <button type="submit" className="btn btn-primary mt-2 w-full">
                    {t("create")}
                  </button>
                </form>
              </div>
            )}

            {/* MODEL DETAIL */}
            {mode === "modelDetail" && selectedModel && (
              <div className="card bg-base-100 shadow-lg rounded-xl p-8">
                <h2 className="text-2xl font-bold mb-4">
                  {selectedModel.dataset} — {selectedModel.labels}
                </h2>
                <button className="btn btn-outline mr-2" onClick={() => setMode("home")}>
                  Back
                </button>
                <button className="btn btn-primary" onClick={startTraining}>
                  Train Model
                </button>
              </div>
            )}

            {/* TRAIN MODEL */}
            {mode === "trainModel" && selectedModel && (
              <div className="card bg-base-100 shadow-lg rounded-xl p-8">
                <h2 className="text-2xl font-bold mb-4">Training {selectedModel.dataset}</h2>
                <textarea
                  className="w-full textarea textarea-bordered h-64 mb-4"
                  value={trainLogs}
                  readOnly
                />
                {trainingFinished && (
                <button onClick={() => navigate(`/models/${modelId}/serve`)}>
                    Serve
                </button>
                )}
              </div>
            )}

            {/* SERVE MODEL */}
            {mode === "serveModel" && selectedModel && (
              <div className="card bg-base-100 shadow-lg rounded-xl p-8">
                <h2 className="text-2xl font-bold mb-4">Serving {selectedModel.dataset}</h2>
                <textarea
                  className="w-full textarea textarea-bordered h-64 mb-4"
                  value={serveLogs}
                  readOnly
                />
              </div>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}