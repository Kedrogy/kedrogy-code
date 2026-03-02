import { useParams, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

function DatasetDetailPage() {
  const { datasetId } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [dataset, setDataset] = useState<any>(null);

  useEffect(() => {
    fetch(`/api/datasets/${datasetId}/`)
      .then(res => res.json())
      .then(data => setDataset(data));
  }, [datasetId]);

  if (!dataset) return <div className="p-8">Loading...</div>;

  return (
    <div className="min-h-screen bg-base-200 font-sans p-8">

      <button
        onClick={() => navigate("/")}
        className="btn btn-sm btn-outline mb-6"
      >
        {t("home")}
      </button>

      <h1 className="text-2xl font-bold mb-6">
        {t("datasetDetailTitle", { name: dataset.dataset_name })}
      </h1>

      <div className="card bg-base-100 shadow-md p-6 mb-6 max-w-3xl">
        <div className="grid gap-4">

          <div className="flex justify-between">
            <span>{t("dataTable")}</span>
            <span>{dataset.data_table_name}</span>
          </div>

          <div className="flex justify-between">
            <span>{t("idField")}</span>
            <span>{dataset.id_field}</span>
          </div>

          <div className="flex justify-between">
            <span>{t("image")}</span>
            <span>{dataset.image}</span>
          </div>

        </div>
      </div>

      <div className="flex gap-2 mb-6">

        <button
          onClick={() => fetch(`/api/datasets/${datasetId}/delete`, { method: "POST" })
            .then(() => navigate("/"))}
          className="btn btn-error btn-sm"
        >
          {t("delete")}
        </button>

        <button
          onClick={() => fetch(`/api/datasets/${datasetId}/label`, { method: "POST" })
            .then(res => res.json())
            .then(data => navigate(`/datasets/create/${data.result_id}`))}
          className="btn btn-primary btn-sm"
        >
          {t("label")}
        </button>

      </div>

    </div>
  );
}

export default DatasetDetailPage;