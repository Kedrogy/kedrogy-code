import { useParams, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { fetchTrainStatus } from "../api";

export default function TrainModelPage() {
  const { modelId, resultId } = useParams<{
    modelId: string;
    resultId: string;
  }>();
  const navigate = useNavigate();

  const [logs, setLogs] = useState("");
  const [status, setStatus] = useState("Training...");
  const [error, setError] = useState("");
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    if (!resultId) return;

    const interval = setInterval(async () => {
      try {
        const data = await fetchTrainStatus(resultId);
        setLogs(data.logs || "");
        setStatus(data.status || "");

        if (data.finished) {
          clearInterval(interval);
          setFinished(true);
        }
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : String(err));
        clearInterval(interval);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [resultId]);

  return (
    <div className="p-8 min-h-screen bg-base-200">
      <h1 className="text-2xl font-bold mb-4">Training Model #{modelId}</h1>

      <p className="mb-2">{status}</p>
      {error && <p className="text-red-500 mb-2">{error}</p>}

      <textarea
        value={logs}
        readOnly
        rows={12}
        className="w-full textarea textarea-bordered font-mono mb-4"
      />

      {finished && (
        <div className="flex gap-2">
          <button
            className="btn btn-success"
            onClick={() => navigate(`/models/${modelId}/serve`)}
          >
            Serve Model
          </button>
          <button
            className="btn btn-outline"
            onClick={() =>
              navigate(`/models/${modelId}`, { state: { trained: true } })
            }
          >
            Back to Model
          </button>
        </div>
      )}
    </div>
  );
}
