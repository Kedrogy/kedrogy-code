import { parseAnnotationData, parseAnnotationSession, type AnnotationData, type AnnotationSession } from "./operations.ts";
import { isRecord } from "./tasks.ts";

type PublicError = { code: string; message: string } | null;
export type ServingStatus = "UNVERIFIED" | "STARTING" | "READY" | "UNAVAILABLE" | "FAILED" | "STOPPING" | "STOPPED";
export interface Serving {
  id: string | null;
  status: ServingStatus;
  training_run_id: string | null;
  labels: string[];
  class_schema_version: 1 | 2 | null;
  conversion_policy: "reject-other-v1" | "single-label-choice-v2" | null;
  observed_at: string | null;
  error: PublicError;
}
const qualityWarnings = ["missing_predicted_classes", "not_above_majority_baseline", "small_validation_sample", "few_training_steps"] as const;
type QualityWarning = typeof qualityWarnings[number];
export interface Quality {
  samples: number; train_samples: number; training_steps: number;
  accuracy: number; macro_f1: number; majority_baseline: number;
  warnings: QualityWarning[];
}
export interface TrainingRun {
  quality: Quality | null;
  id: string;
  status: string;
  is_finished: boolean;
  labels: string[];
  created_at: string;
  finished_at: string | null;
  error: PublicError;
  published?: boolean;
  served?: boolean;
}
export interface Model {
  pending_cleanup: string | null;
  id: number;
  on_dataset: number;
  model_name: string;
  dataset_name: string;
  labels: string[];
  labels_valid: boolean;
  a_preprocess_fun: string;
  trained: boolean;
  served: boolean;
  artifact_status: string;
  published_run: string | null;
  serving: Serving;
  last_training_run: TrainingRun | null;
}
export interface Dataset {
  pending_cleanup: string | null;
  id: number;
  display_name: string;
  dataset_name: string;
  prodigy_dataset_name: string | null;
  annotation_policy: "reject-other-v1" | "single-label-choice-v2";
  binding_state: "PENDING" | "BOUND" | "UNRESOLVED";
  image: string;
  workingDir: string;
  pipeline: string;
  recipe_options: string;
  data_table_name: string;
  id_field: string;
  labelled: boolean;
  annotation_data: AnnotationData;
  annotation_session: AnnotationSession;
  deletion_pending: boolean;
  annotations_deleted: boolean;
}

function invalid(): never { throw new Error("The server returned an invalid model or dataset response."); }
function object(value: unknown): Record<string, unknown> { return isRecord(value) ? value : invalid(); }
function string(value: unknown): string { return typeof value === "string" ? value : invalid(); }
function nullableString(value: unknown): string | null { return value === null ? null : string(value); }
function boolean(value: unknown): boolean { return typeof value === "boolean" ? value : invalid(); }
function integer(value: unknown): number { return typeof value === "number" && Number.isSafeInteger(value) ? value : invalid(); }
function strings(value: unknown): string[] { return Array.isArray(value) ? value.map(string) : invalid(); }
function publicError(value: unknown): PublicError {
  if (value === null) return null;
  const data = object(value);
  return { code: string(data.code), message: string(data.message) };
}
export function parseServing(value: unknown): Serving {
  const data = object(value);
  const status = string(data.status);
  if (status !== "UNVERIFIED" && status !== "STARTING" && status !== "READY" && status !== "UNAVAILABLE" && status !== "FAILED" && status !== "STOPPING" && status !== "STOPPED") return invalid();
  const version = data.class_schema_version;
  const policy = data.conversion_policy;
  if (policy !== null && policy !== "reject-other-v1" && policy !== "single-label-choice-v2") return invalid();
  if (version !== null && version !== 1 && version !== 2) return invalid();
  if ((version === null && policy !== null) || (version === 1 && policy !== "reject-other-v1")
      || (version === 2 && policy !== "single-label-choice-v2")) return invalid();
  if (status === "READY" && (version === null || typeof data.id !== "string" || typeof data.training_run_id !== "string")) return invalid();
  return { id: nullableString(data.id), status, class_schema_version: version, conversion_policy: policy, training_run_id: nullableString(data.training_run_id),
    labels: strings(data.labels), observed_at: nullableString(data.observed_at), error: publicError(data.error) };
}
export function parseQuality(value: unknown): Quality | null {
  if (value === undefined || value === null) return null;
  const data = object(value);
  if (data.version !== 1 || data.split !== "validation") return invalid();
  const fraction = (value: unknown) => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1 ? value : invalid();
  const positive = (value: unknown) => { const result = integer(value); return result > 0 ? result : invalid(); };
  const warnings = strings(data.warnings).map(warning => {
    const known = qualityWarnings.find(value => value === warning);
    return known ?? invalid();
  });
  return { samples: positive(data.samples), train_samples: positive(data.train_samples),
    training_steps: positive(data.training_steps), accuracy: fraction(data.accuracy),
    macro_f1: fraction(data.macro_f1), majority_baseline: fraction(data.majority_baseline), warnings };
}
export function parseRun(value: unknown): TrainingRun {
  const data = object(value);
  return { quality: parseQuality(data.quality), id: string(data.id), status: string(data.status), is_finished: boolean(data.is_finished),
    labels: strings(data.labels), created_at: string(data.created_at), finished_at: nullableString(data.finished_at),
    error: publicError(data.error), published: data.published === undefined ? undefined : boolean(data.published),
    served: data.served === undefined ? undefined : boolean(data.served) };
}
export function parseRuns(value: unknown): TrainingRun[] { return Array.isArray(value) ? value.map(parseRun) : invalid(); }
export function parseModel(value: unknown): Model {
  const data = object(value);
  const serving = parseServing(data.serving);
  const served = boolean(data.served);
  if (served !== (serving.status === "READY")) return invalid();
  return { pending_cleanup: nullableString(data.pending_cleanup), id: integer(data.id), on_dataset: integer(data.on_dataset), model_name: string(data.model_name),
    dataset_name: string(data.dataset_name), labels: strings(data.labels), labels_valid: boolean(data.labels_valid),
    a_preprocess_fun: string(data.a_preprocess_fun), trained: boolean(data.trained), served,
    artifact_status: string(data.artifact_status), published_run: nullableString(data.published_run), serving,
    last_training_run: data.last_training_run === null ? null : parseRun(data.last_training_run) };
}
export function parseDataset(value: unknown): Dataset {
  const data = object(value);
  const binding = string(data.binding_state);
  if (binding !== "PENDING" && binding !== "BOUND" && binding !== "UNRESOLVED") return invalid();
  const policy = data.annotation_policy;
  if (policy !== "reject-other-v1" && policy !== "single-label-choice-v2") return invalid();
  return { annotation_policy: policy, pending_cleanup: nullableString(data.pending_cleanup), id: integer(data.id), display_name: string(data.display_name), dataset_name: string(data.dataset_name),
    prodigy_dataset_name: nullableString(data.prodigy_dataset_name), binding_state: binding,
    image: string(data.image), workingDir: string(data.workingDir), pipeline: string(data.pipeline),
    recipe_options: string(data.recipe_options), data_table_name: string(data.data_table_name),
    id_field: string(data.id_field), labelled: boolean(data.labelled),
    annotation_data: parseAnnotationData(data.annotation_data), annotation_session: parseAnnotationSession(data.annotation_session),
    deletion_pending: boolean(data.deletion_pending), annotations_deleted: boolean(data.annotations_deleted) };
}
export function parsePrediction(value: unknown, serving: Serving): string {
  const data = object(value);
  const index = integer(data.class_id);
  const label = string(data.label);
  const mapping = serving.class_schema_version === 1 ? ["OTHER", ...serving.labels] : serving.labels;
  if (serving.class_schema_version === null || (serving.class_schema_version === 2 && data.class_schema_version !== 2)
      || (serving.class_schema_version === 1 && data.class_schema_version !== undefined && data.class_schema_version !== 1)
      || data.contract_version !== 1 || data.training_run_id !== serving.training_run_id || data.serving_run_id !== serving.id
      || index < 0 || index >= mapping.length || label !== mapping[index]) return invalid();
  return label;
}
