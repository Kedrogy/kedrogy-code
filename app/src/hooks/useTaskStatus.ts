import { useEffect, useState } from "react";
import { API } from "../api";
import { parseTaskResult, responseError } from "../api/tasks";
import type { TaskKind, TaskResult } from "../api/tasks";

interface Observation {
  key: string;
  result: TaskResult | null;
  error: string;
}

export function useTaskStatus(kind: TaskKind, resultId: string | undefined) {
  const key = `${kind}:${resultId ?? ""}`;
  const [observation, setObservation] = useState<Observation>({ key: "", result: null, error: "" });
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!resultId) return;
    const taskId = resultId;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const response = await fetch(`${API}/api/tasks/${kind}/${encodeURIComponent(taskId)}/status/`, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]) });
        if (!response.ok) throw new Error(await responseError(response));
        const data = parseTaskResult(await response.json());
        if (controller.signal.aborted) return;
        setObservation({ key, result: data, error: "" });
        if (!data.is_finished) timer = setTimeout(() => { void poll(); }, 2000);
      } catch (error: unknown) {
        if (!controller.signal.aborted) {
          const message = error instanceof DOMException && error.name === "TimeoutError"
            ? "Status request timed out. Retry the check."
            : error instanceof Error ? error.message : "Could not read the task status.";
          setObservation(previous => ({ key, result: previous.key === key ? previous.result : null, error: message }));
        }
      }
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [key, kind, resultId, retry]);
  return {
    result: observation.key === key ? observation.result : null,
    connectionError: observation.key === key ? observation.error : "",
    retry: () => setRetry(value => value + 1),
  };
}
