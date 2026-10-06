import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { TaskProgress } from "../components/TaskProgress";

export default function TrainModelPage() {
  const { t } = useTranslation();
  const { resultId, modelId } = useParams();
  return <TaskProgress kind="train" resultId={resultId} title={t("trainingTitle", { id: modelId })} backTo={`/models/${modelId}`} />;
}
