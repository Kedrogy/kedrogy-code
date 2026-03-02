import { useParams, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

export default function TrainModelPage() {
  const { modelId } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [taskId, setTaskId] = useState<string | null>(null);
  const [logs, setLogs] = useState("");
  const [status, setStatus] = useState("Starting training...");
  const [error, setError] = useState("");

  useEffect(() => {
    async function startTraining() {
      try {
        const res = await fetch(`/api/models/${modelId}/train/`, {
          method: "POST",
        });

        if (!res.ok) throw new Error("Failed to start training");

        const data = await res.json();
        setTaskId(data.task_id);
      } catch (err: any) {
        setError(err.message);
      }
    }

    startTraining();
  }, [modelId]);

  useEffect(() => {
    if (!taskId) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/tasks/${taskId}/`);
        const data = await res.json();

        setLogs(data.logs || "");
        setStatus(data.status || "");

        if (data.status === "finished") {
          clearInterval(interval);
          navigate(`/models/${modelId}`);
        }

        if (data.status === "failed") {
          clearInterval(interval);
          setError("Training failed");
        }
      } catch (err) {
        console.error(err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [taskId, modelId, navigate]);

  return (
    <div className="p-8 min-h-screen bg-base-200">
      <h1 className="text-2xl font-bold mb-4">
        {t("Training model")} #{modelId}
      </h1>

      {status && <p className="mb-2">{status}</p>}
      {error && <p className="text-red-500">{error}</p>}

      <textarea
        value={logs}
        readOnly
        rows={12}
        className="w-full textarea textarea-bordered"
      />
    </div>
  );
}