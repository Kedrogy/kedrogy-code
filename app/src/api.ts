// Shared API module — all backend calls go through here.
//
// JSON API endpoints (all csrf_exempt):
//   GET  /api/index/                          -> { datasets, models, latest_dataset }
//   POST /api/datasets/create/                -> { id, dataset_name }
//   GET  /api/datasets/<id>/                  -> dataset detail
//   GET  /api/datasets/result/<result_id>/    -> { finished, status, logs, ... }
//   POST /api/datasets/<id>/models/create/    -> { id }
//   POST /api/models/<id>/train/              -> { status, result_id }
//   POST /api/models/<id>/serve/              -> { status, result_id }
//   GET  /api/train/result/<result_id>/       -> { finished, status, logs }
//   GET  /api/serve/result/<result_id>/       -> { finished, status, logs }

// ── Types ──────────────────────────────────────────────

export interface Dataset {
  id: number;
  dataset_name: string;
  data_table_name: string;
  id_field: string;
  image: string;
  workingDir: string;
  pipeline: string;
  recipe_options: string;
}

export interface Model {
  id: number;
  on_dataset_id: number;
  dataset_name: string;
  labels: string;
  a_preprocess_fun: string;
  trained: boolean;
  served: boolean;
}

export interface IndexData {
  datasets: Dataset[];
  models: Model[];
  latest_dataset: { name: string; id: number } | null;
}

export interface TaskStatus {
  finished: boolean;
  status: string;
  logs: string;
}

export interface DatasetTaskStatus extends TaskStatus {
  result?: Record<string, unknown>;
  dataset_name?: string;
  dataset_id?: number;
}

// ── Index API (list all datasets + models) ─────────────

export async function fetchIndex(): Promise<IndexData> {
  const res = await fetch("/api/index/");
  if (!res.ok) throw new Error(`Failed to fetch index: ${res.status}`);
  return res.json();
}

// ── Dataset APIs ───────────────────────────────────────

export async function fetchDataset(
  datasetId: number | string
): Promise<Dataset> {
  const res = await fetch(`/api/datasets/${datasetId}/`);
  if (!res.ok) throw new Error(`Failed to fetch dataset: ${res.status}`);
  return res.json();
}

export async function createDataset(
  fields: Record<string, string>
): Promise<number> {
  const res = await fetch("/api/datasets/create/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  if (!res.ok) throw new Error(`Failed to create dataset: ${res.status}`);
  const data = await res.json();
  return data.id;
}

export async function labelDataset(
  datasetId: number | string
): Promise<string> {
  const res = await fetch(`/api/datasets/${datasetId}/label/`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to start labeling: ${res.status}`);
  const data = await res.json();
  return data.result_id;
}

export async function deleteDataset(
  datasetId: number | string
): Promise<void> {
  const res = await fetch(`/api/datasets/${datasetId}/delete/`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to delete dataset: ${res.status}`);
}

export async function fetchDatasetTaskStatus(
  resultId: string
): Promise<DatasetTaskStatus> {
  const res = await fetch(`/api/datasets/result/${resultId}/`);
  if (!res.ok) throw new Error(`Failed to fetch task status: ${res.status}`);
  return res.json();
}

// ── Model APIs ─────────────────────────────────────────

export async function createModel(
  datasetId: number | string,
  labels: string,
  preprocessFun: string
): Promise<number> {
  const res = await fetch(`/api/datasets/${datasetId}/models/create/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ labels, a_preprocess_fun: preprocessFun }),
  });
  if (!res.ok) throw new Error(`Failed to create model: ${res.status}`);
  const data = await res.json();
  return data.id;
}

export async function startTraining(
  modelId: number | string
): Promise<string> {
  const res = await fetch(`/api/models/${modelId}/train/`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to start training: ${res.status}`);
  const data = await res.json();
  return data.result_id;
}

export async function fetchTrainStatus(resultId: string): Promise<TaskStatus> {
  const res = await fetch(`/api/train/result/${resultId}/`);
  if (!res.ok)
    throw new Error(`Failed to fetch training status: ${res.status}`);
  return res.json();
}

export async function startServing(modelId: number | string): Promise<string> {
  const res = await fetch(`/api/models/${modelId}/serve/`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to start serving: ${res.status}`);
  const data = await res.json();
  return data.result_id;
}

export async function fetchServeStatus(resultId: string): Promise<TaskStatus> {
  const res = await fetch(`/api/serve/result/${resultId}/`);
  if (!res.ok)
    throw new Error(`Failed to fetch serving status: ${res.status}`);
  return res.json();
}

export async function predictModel(
  modelId: number | string,
  textInput: string
): Promise<string> {
  const res = await fetch(`/api/models/${modelId}/predict/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text_input: textInput }),
  });
  if (!res.ok) throw new Error(`Prediction failed: ${res.status}`);
  const data = await res.json();
  return data.predicted_class;
}
