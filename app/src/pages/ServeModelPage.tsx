import { useParams, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { startServing, fetchServeStatus, predictModel } from "../api";

export default function ServeModelPage() {
  const { modelId } = useParams<{ modelId: string }>();
  const navigate = useNavigate();

  // ── Serve deployment state ──
  const [resultId, setResultId] = useState<string | null>(null);
  const [logs, setLogs] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [finished, setFinished] = useState(false);
  const [starting, setStarting] = useState(false);

  // ── Predict state ──
  const [textInput, setTextInput] = useState("");
  const [prediction, setPrediction] = useState<string | null>(null);
  const [predicting, setPredicting] = useState(false);

  const handleStartServing = async () => {
    if (!modelId) return;
    setStarting(true);
    setError("");
    try {
      const id = await startServing(modelId);
      setResultId(id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setStarting(false);
    }
  };

  // Poll serving status once we have a resultId
  useEffect(() => {
    if (!resultId) return;

    const interval = setInterval(async () => {
      try {
        const data = await fetchServeStatus(resultId);
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

  const handlePredict = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!modelId) return;
    setPredicting(true);
    setPrediction(null);
    setError("");
    try {
      const result = await predictModel(modelId, textInput);
      setPrediction(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPredicting(false);
    }
  };

  return (
    <div className="p-8 min-h-screen bg-base-200">
      <h1 className="text-2xl font-bold mb-4">Serve Model #{modelId}</h1>

      {/* Start serving */}
      {!resultId && !finished && (
        <button
          className="btn btn-primary mb-4"
          onClick={handleStartServing}
          disabled={starting}
        >
          {starting ? "Starting..." : "Start Serving"}
        </button>
      )}

      {error && <p className="text-red-500 mb-2">{error}</p>}
      {status && !finished && <p className="mb-2">{status}</p>}

      {resultId && !finished && (
        <textarea
          value={logs}
          readOnly
          rows={12}
          className="w-full textarea textarea-bordered font-mono mb-4"
        />
      )}

      {finished && (
        <>
          <div className="alert alert-success mb-6">
            Model is now being served.
          </div>

          {/* Predict / text input */}
          <div className="card bg-base-100 shadow-lg p-6 mb-6 max-w-3xl">
            <h2 className="text-xl font-semibold mb-4">Text Input</h2>
            <form onSubmit={handlePredict}>
              <textarea
                rows={4}
                className="textarea textarea-bordered w-full mb-4"
                placeholder="Enter text here..."
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
              />
              <button
                type="submit"
                className="btn btn-primary"
                disabled={predicting || !textInput.trim()}
              >
                {predicting ? "Predicting..." : "Predict"}
              </button>
            </form>

            {prediction && (
              <div className="alert alert-success mt-4">
                Prediction: <strong>{prediction}</strong>
              </div>
            )}
          </div>
        </>
      )}

      <button
        className="btn btn-outline"
        onClick={() =>
          navigate(`/models/${modelId}`, { state: { trained: true } })
        }
      >
        Back to Model
      </button>
    </div>
  );
}
