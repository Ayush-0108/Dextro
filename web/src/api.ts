import type { Answer, Dataset, Health, HistoryEntry } from "./types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 300)}`);
  return r.json() as Promise<T>;
}

export const getDatasets = () => call<{ default: string; datasets: Dataset[] }>("/api/datasets");
export const getHealth = (dataset: string) => call<Health>(`/api/health?dataset=${encodeURIComponent(dataset)}`);
export const ask = (question: string, dataset: string, role: "analyst" | "restricted", history: HistoryEntry[]) =>
  call<Answer>("/api/ask", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, dataset, role, history }),
  });
