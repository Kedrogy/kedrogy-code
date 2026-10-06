import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { TaskProgress } from "../components/TaskProgress";

export default function CreateDatasetTaskPage() {
  const { t } = useTranslation();
  const { resultId } = useParams();
  return <TaskProgress kind="label" resultId={resultId} title={t("preparingAnnotation")} backTo={`/`} />;
}
