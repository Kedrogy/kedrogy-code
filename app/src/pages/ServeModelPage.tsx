import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { TaskProgress } from "../components/TaskProgress";

export default function ServeModelPage() {
  const { t } = useTranslation();
  const { resultId, modelId } = useParams();
  return <TaskProgress kind="serve" resultId={resultId} title={t("servingTitle", { id: modelId })} backTo={`/models/${modelId}`} />;
}
