import { useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

function DeleteModelPage() {
  const { id } = useParams();
  const { t } = useTranslation();
  const [logs, setLogs] = useState("");

  useEffect(() => {
    const interval = setInterval(() => {
      fetch(`/api/models/${id}/delete-status`)
        .then(res => res.text())
        .then(data => setLogs(data));
    }, 1000);

    return () => clearInterval(interval);
  }, [id]);

  return (
    <div className="p-8">
      <a href="/" className="btn btn-sm btn-outline mb-6 inline-block">
        HOME
      </a>

      <h1 className="text-2xl font-bold mb-6">
        {t("deletingModel", { id })}
      </h1>

      <p className="mb-6">{t("tbw")}</p>

      <label className="font-medium">{t("result")}</label>

      <textarea
        value={logs}
        readOnly
        rows={20}
        className="textarea textarea-bordered w-full resize-none mt-2 mb-4 font-mono"
      />
    </div>
  );
}

export default DeleteModelPage;