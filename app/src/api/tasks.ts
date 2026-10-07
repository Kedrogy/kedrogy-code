import { parseAnnotationSession, type AnnotationSession } from "./operations.ts";

export type TaskKind = "train" | "serve" | "label" | "delete";
export type TaskStatus = "READY" | "QUEUED" | "RUNNING" | "VERIFYING" | "SUCCEEDED" | "FAILED" | "TIMED_OUT" | "INTERRUPTED" | "RETRY_WAIT" | "NEEDS_REVIEW";
export interface TaskResult {
  status: TaskStatus;
  is_finished: boolean;
  logs: string;
  step?: string;
  can_retry?: boolean;
  progress?: { completed: number; total: number };
  session?: AnnotationSession;
  error: { code: string; message: string } | null;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isTaskStatus(value: unknown): value is TaskStatus {
  return value === "READY" || value === "QUEUED" || value === "RUNNING" || value === "VERIFYING" || value === "SUCCEEDED" || value === "FAILED" || value === "TIMED_OUT" || value === "INTERRUPTED" || value === "RETRY_WAIT" || value === "NEEDS_REVIEW";
}

export function parseTaskResult(value: unknown): TaskResult {
  if (!isRecord(value) || !isTaskStatus(value.status) || typeof value.is_finished !== "boolean" || typeof value.logs !== "string") {
    throw new Error("The server returned an invalid task status.");
  }
  const terminal = ["SUCCEEDED", "FAILED", "TIMED_OUT", "INTERRUPTED", "NEEDS_REVIEW"].includes(value.status);
  if (terminal !== value.is_finished) throw new Error("The server returned an inconsistent task status.");
  const error = value.error;
  let checkedError: TaskResult["error"] = null;
  if (error !== null) {
    if (!isRecord(error) || typeof error.code !== "string" || typeof error.message !== "string") {
      throw new Error("The server returned an invalid task error.");
    }
    checkedError = { code: error.code, message: error.message };
  }
  if (value.step !== undefined && typeof value.step !== "string") throw new Error("Invalid cleanup step.");
  if (value.can_retry !== undefined && typeof value.can_retry !== "boolean") throw new Error("Invalid retry capability.");
  const p = value.progress;
  let progress: TaskResult["progress"];
  if (p !== undefined) {
    if (!isRecord(p) || typeof p.completed !== "number" || typeof p.total !== "number" || !Number.isSafeInteger(p.completed)
        || !Number.isSafeInteger(p.total) || p.completed < 0 || p.total < p.completed) throw new Error("Invalid cleanup progress.");
    progress = { completed: p.completed, total: p.total };
  }
  return { session: value.session === undefined ? undefined : parseAnnotationSession(value.session), step: value.step, can_retry: value.can_retry, progress, status: value.status, is_finished: terminal, logs: value.logs, error: checkedError };
}

export async function responseError(response: Response): Promise<string> {
  try {
    const data: unknown = await response.json();
    if (isRecord(data)) {
      if (isRecord(data.fields)) {
        const fields = Object.entries(data.fields).flatMap(([key, value]) =>
          Array.isArray(value) && value.every(item => typeof item === "string") ? [`${key}: ${value.join(" ")}`] : []);
        if (fields.length) return fields.join(" ");
      }
      if (isRecord(data.error) && typeof data.error.message === "string") return data.error.message;
    }
  } catch { /* An HTML or empty response still has an HTTP status. */ }
  return `Request failed (HTTP ${response.status}).`;
}
