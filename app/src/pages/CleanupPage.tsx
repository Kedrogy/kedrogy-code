import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { DeletionReview } from "../components/DeletionReview";

export default function CleanupPage() {
  const { t } = useTranslation();
  const { target, id, action } = useParams();
  if ((target !== "models" && target !== "datasets") || !id || !/^\d+$/.test(id)
      || (action !== "model" && action !== "model_files" && action !== "dataset" && action !== "annotations")) return <p role="alert">{t("invalidCleanupTarget")}</p>;
  return <DeletionReview target={target} id={id} action={action} />;
}
