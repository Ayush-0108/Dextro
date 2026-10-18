// Mirrors api/server.py (POST /api/ask): built from the pipeline's own Answer, nothing invented client-side.
export type Status = "answered" | "empty" | "clarify" | "not_in_data" | "refused" | "chitchat" | "error";

export interface NumberCheck {
  text: string; value: number; status: "verified" | "derived" | "context" | "unverified";
  source: string; cell: [number, string] | null; start: number; end: number;
}
export interface CoverageItem { asked: string; found: boolean; where: string }
export interface QueryResult {
  sql: string; columns: string[]; rows: (string | number | null)[][]; truncated: boolean; query_id: string | null;
  elapsed_ms: number; engine: string; role: string | null; error: string | null; row_count?: number; warehouse?: string;
}
export interface Candidate {
  name: string; sql: string | null; plan: Record<string, unknown> | null; notes: string[]; error: string | null;
  attempts: { stage: string; error?: string | null; query_id?: string | null }[]; issues: string[];
  result: QueryResult | null;
}
export interface HistoryEntry { question: string; standalone_question: string; summary: string; sql: string | null }
export interface Answer {
  answer_id: string; question: string; standalone_question: string; status: Status; message: string;
  confidence: "high" | "medium" | "low" | null; agreement: string; assumptions: string[]; interpretations: string[];
  chosen: { name: string; sql: string } | null; candidates: Candidate[];
  alternatives: { candidate?: string; sql?: string; summary?: string; note?: string; issues?: string[] }[];
  explanation: string[]; number_checks: NumberCheck[]; checks: string[]; coverage: CoverageItem[];
  narration: string; timings: Record<string, number>; model: string; engine: string; role: string | null;
  result: QueryResult | null; history_entry: HistoryEntry;
}
export interface EntityColumn {
  name: string;
  type: string;
  description?: string;
  values?: string[];
  synonyms?: string[];
}
export interface Entity {
  alias: string;
  table: string;
  description?: string;
  primary_key?: string[];
  columns: EntityColumn[];
}
export interface Metric {
  name: string;
  formula: string;
  description?: string;
}
export interface Dataset {
  id: string;
  path: string;
  title: string;
  coverage: string;
  tables: number;
  sample_questions: string[];
  description?: string;
  entities?: Entity[];
  metrics?: Metric[];
}
export interface HealthItem { state: "ok" | "warn" | "bad"; label: string; detail?: string; warehouse?: string; region?: string; version?: string }
export type Health = Record<string, HealthItem>;
