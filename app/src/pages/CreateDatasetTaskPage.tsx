import { useParams, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { API } from "../api";

function CreateDatasetTaskPage() {
  const { resultId } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [logs, setLogs] = useState("");
  const [status, setStatus] = useState("Starting...");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!resultId) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API}/api/tasks/label/${resultId}/status/`);
        if (!res.ok) throw new Error("Failed to poll status");
        const data = await res.json();

        setLogs(data.logs || "");
        setStatus(data.status || "");

        if (data.is_finished) {
          clearInterval(interval);
          setStatus("Done!");
          setTimeout(() => navigate("/"), 1500);
        }
      } catch (err: any) {
        clearInterval(interval);
        setError(err.message);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [resultId, navigate]);

  return (
    <div className="min-h-screen bg-base-200 p-8">
      <button onClick={() => navigate("/")} className="btn btn-sm btn-outline mb-6">
        {t("home")}
      </button>

      <div className="card bg-base-100 shadow-lg">
        <div className="card-body">
          <h2 className="card-title">{t("creatingDataset") || "Creating Dataset"}</h2>
          <p>Status: <span className="badge badge-primary">{status}</span></p>
          {error && <div className="alert alert-error">{error}</div>}
          <fieldset className="fieldset">
            <legend className="fieldset-legend">{t("result") || "Logs"}</legend>
            <textarea
              value={logs}
              readOnly
              rows={16}
              className="textarea textarea-bordered w-full font-mono"
            />
          </fieldset>
        </div>
      </div>
    </div>
  );
}

export default CreateDatasetTaskPage;
