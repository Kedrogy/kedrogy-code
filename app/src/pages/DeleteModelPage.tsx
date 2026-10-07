import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { TaskProgress } from "../components/TaskProgress";

export default function DeleteModelPage() {
  const { t } = useTranslation();
  const { resultId, modelId } = useParams();
  return <TaskProgress kind="delete" resultId={resultId} title={modelId ? t("cleanupTitle", { id: modelId }) : t("cleanupOperation")} backTo={`/`} />;
}
