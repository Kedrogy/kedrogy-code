import { useParams, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

export default function ServeModelPage() {
  const { modelId } = useParams();
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  async function startServing() {
    try {
      const res = await fetch(`/api/models/${modelId}/serve/`, {
        method: "POST",
      });

      if (!res.ok) throw new Error("Failed to start serving");

      const data = await res.json();
      setStatus(data.message || "Model deployed successfully");
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div className="p-8">
      <h1 className="text-xl font-bold mb-4">Serve Model #{modelId}</h1>

      <button className="btn btn-primary mb-4" onClick={startServing}>
        Start Serving
      </button>

      {status && <p>{status}</p>}
      {error && <p className="text-red-500">{error}</p>}
    </div>
  );
}