import { isRecord } from "./tasks.ts";

export interface AnnotationSession {
  id: string | null;
  dataset_id: number | null;
  status: "UNVERIFIED" | "STARTING" | "READY" | "UNAVAILABLE" | "STOPPING" | "STOPPED";
  url: string | null;
  observed_at: string | null;
  error: { code: string; message: string } | null;
}
export interface AnnotationData {
  status: "UNKNOWN" | "EMPTY" | "PRESENT" | "INVALID";
  counts: { total: number; accepted: number; rejected: number; ignored: number; invalid: number } | null;
  observed_at: string | null;
  refresh_requested: boolean;
  error: { code: string; message: string } | null;
}
export interface DeletionPreview {
  action: string;
  target: string;
  model_ids: number[];
  resources: { kind: string; name: string; namespace: string; uid: string }[];
  issues: string[];
  preview_token: string;
  retains_annotations: boolean;
  retains_source_rows: true;
  legacy_review_model_ids: number[];
}
export interface LegacyCleanupReview {
  model_id: number;
  namespace: string;
  resources: DeletionPreview["resources"];
  issues: string[];
  evidence: string[];
  review_token: string;
}
function invalid(): never { throw new Error("The server returned an invalid operation response."); }
function nullableText(value: unknown): string | null { return value === null || typeof value === "string" ? value : invalid(); }
function error(value: unknown): AnnotationSession["error"] {
  if (value === null) return null;
  if (!isRecord(value) || typeof value.code !== "string" || typeof value.message !== "string") return invalid();
  return { code: value.code, message: value.message };
}
function count(value: unknown): number { return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : invalid(); }
export function parseAnnotationSession(value: unknown): AnnotationSession {
  if (!isRecord(value)) return invalid();
  const state = value.status;
  if (state !== "UNVERIFIED" && state !== "STARTING" && state !== "READY" && state !== "UNAVAILABLE" && state !== "STOPPING" && state !== "STOPPED") return invalid();
  const url = nullableText(value.url);
  if (url !== null && (!/^https?:\/\//.test(url) || state !== "READY")) return invalid();
  return { id: nullableText(value.id), dataset_id: value.dataset_id === null ? null : count(value.dataset_id), status: state,
    url, observed_at: nullableText(value.observed_at), error: error(value.error) };
}
export function parseAnnotationData(value: unknown): AnnotationData {
  if (!isRecord(value) || typeof value.refresh_requested !== "boolean") return invalid();
  const state = value.status;
  if (state !== "UNKNOWN" && state !== "EMPTY" && state !== "PRESENT" && state !== "INVALID") return invalid();
  const c = value.counts;
  if (c !== null && !isRecord(c)) return invalid();
  const counts = c === null ? null : { total: count(c.total), accepted: count(c.accepted), rejected: count(c.rejected), ignored: count(c.ignored), invalid: count(c.invalid) };
  if (counts && counts.total !== counts.accepted + counts.rejected + counts.ignored + counts.invalid) return invalid();
  return { status: state, counts, observed_at: nullableText(value.observed_at), refresh_requested: value.refresh_requested, error: error(value.error) };
}
export function parseDeletionPreview(value: unknown): DeletionPreview {
  if (!isRecord(value) || typeof value.action !== "string" || typeof value.target !== "string" || typeof value.preview_token !== "string"
      || typeof value.retains_annotations !== "boolean" || value.retains_source_rows !== true || !Array.isArray(value.model_ids)
      || !Array.isArray(value.resources) || !Array.isArray(value.issues) || !value.issues.every(v => typeof v === "string")) return invalid();
  const resources = value.resources.map(v => {
    if (!isRecord(v) || typeof v.kind !== "string" || typeof v.name !== "string" || typeof v.namespace !== "string" || typeof v.uid !== "string") return invalid();
    return { kind: v.kind, name: v.name, namespace: v.namespace, uid: v.uid };
  });
  return { action: value.action, target: value.target, model_ids: value.model_ids.map(count), resources, issues: value.issues,
    preview_token: value.preview_token, retains_annotations: value.retains_annotations, retains_source_rows: true,
    legacy_review_model_ids: value.legacy_review_model_ids === undefined ? [] :
      Array.isArray(value.legacy_review_model_ids) ? value.legacy_review_model_ids.map(count) : invalid() };
}

export function parseLegacyCleanupReview(value: unknown): LegacyCleanupReview {
  if (!isRecord(value) || typeof value.namespace !== "string" || typeof value.review_token !== "string"
      || !Array.isArray(value.resources) || !Array.isArray(value.issues) || !value.issues.every(v => typeof v === "string")
      || !Array.isArray(value.evidence) || !value.evidence.every(v => typeof v === "string")) return invalid();
  const namespace = value.namespace;
  const resources = value.resources.map(v => {
    if (!isRecord(v) || typeof v.kind !== "string" || typeof v.name !== "string"
        || v.namespace !== namespace || typeof v.uid !== "string" || !v.uid) return invalid();
    return {kind: v.kind, name: v.name, namespace, uid: v.uid};
  });
  return {model_id: count(value.model_id), namespace: value.namespace, review_token: value.review_token,
    resources, issues: value.issues, evidence: value.evidence};
}
