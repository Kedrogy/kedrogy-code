import { useParams, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchDatasetTaskStatus } from "../api";

export default function CreateDatasetTaskPage() {
  const { resultId } = useParams<{ resultId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [logs, setLogs] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!resultId) return;

    const interval = setInterval(async () => {
      try {
        const data = await fetchDatasetTaskStatus(resultId);
        setLogs(data.logs || "");
        setStatus(data.status || "");

        if (data.finished) {
          clearInterval(interval);
          if (data.dataset_id) {
            navigate(`/datasets/${data.dataset_id}`);
          } else {
            navigate("/");
          }
        }
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : String(err));
        clearInterval(interval);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [resultId, navigate]);

  return (
    <div className="p-8 min-h-screen bg-base-200">
      <h1 className="text-2xl font-bold mb-4">{t("creatingDataset")}</h1>

      {error && <p className="text-red-500 mb-4">{error}</p>}
      <p className="mb-4">{status}</p>

      <textarea
        value={logs}
        readOnly
        rows={10}
        className="w-full textarea textarea-bordered font-mono"
      />
    </div>
  );
}
