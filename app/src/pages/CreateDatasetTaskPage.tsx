import { useParams, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

function CreateDatasetTaskPage() {
  const { resultId } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [logs, setLogs] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    const interval = setInterval(() => {
      fetch(`/api/datasets/result/${resultId}/`)
        .then(res => res.json())
        .then(data => {
          setLogs(data.logs);

          if (!data.finished) {
            setStatus(data.status);
          }

          if (data.finished) {
            clearInterval(interval);
            navigate("/");
          }
        });
    }, 1000);

    return () => clearInterval(interval);
  }, [resultId, navigate]);

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">
        {t("creatingDataset")}
      </h1>

      <p className="mb-4">{status}</p>

      <textarea
        value={logs}
        readOnly
        rows={10}
        className="w-full textarea textarea-bordered"
      />
    </div>
  );
}

export default CreateDatasetTaskPage;