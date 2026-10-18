import { useState } from "react";
import type { Dataset } from "../types";
import { DatabaseIcon, TableIcon, KeyIcon, SparkleIcon, PaperclipIcon } from "./icons";

const TYPE_STYLES: Record<string, string> = {
  id: "bg-blue-50 text-blue-700 border-blue-200",
  number: "bg-purple-50 text-purple-700 border-purple-200",
  category: "bg-emerald-50 text-emerald-700 border-emerald-200",
  date: "bg-amber-50 text-amber-700 border-amber-200",
  text: "bg-stone-100 text-stone-700 border-stone-200",
};

export default function DataExplorer({
  dataset,
  onAskQuestion,
  onOpenUpload,
}: {
  dataset: Dataset | undefined;
  onAskQuestion: (q: string) => void;
  onOpenUpload?: () => void;
}) {
  const entities = dataset?.entities || [];
  const [selectedIdx, setSelectedIdx] = useState(0);

  if (!dataset) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-stone-500">
        No dataset selected.
      </div>
    );
  }

  const activeEntity = entities[selectedIdx] || entities[0];

  return (
    <div className="flex h-full flex-col overflow-hidden bg-[#FAFAF9]">
      {/* Top Banner */}
      <div className="border-b border-stone-200/80 bg-white px-8 py-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-stone-100 text-stone-700">
                <DatabaseIcon className="h-4 w-4" />
              </span>
              <h2 className="text-xl font-bold tracking-tight text-stone-900">
                {dataset.title}
              </h2>
              <span className="rounded-full bg-stone-100 px-2.5 py-0.5 text-xs font-semibold text-stone-600">
                {entities.length} tables
              </span>
            </div>
            <p className="mt-1 text-xs text-stone-500">
              {dataset.coverage || dataset.description || "Live schema and table relationships."}
            </p>
          </div>
          {onOpenUpload && (
            <button
              onClick={onOpenUpload}
              className="flex items-center gap-1.5 rounded-lg border border-stone-200 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700 shadow-sm hover:bg-stone-50 transition"
            >
              <PaperclipIcon className="h-3.5 w-3.5 text-emerald-600" />
              <span>+ Upload New CSV</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Split Content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Table Selector Sidebar */}
        <aside className="w-64 border-r border-stone-200/80 bg-white/70 p-4 overflow-y-auto">
          <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-stone-400">
            Tables in Schema
          </div>
          <div className="space-y-1">
            {entities.map((e, i) => {
              const active = i === selectedIdx;
              return (
                <button
                  key={e.alias}
                  onClick={() => setSelectedIdx(i)}
                  className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition-all ${
                    active
                      ? "bg-stone-900 text-white font-medium shadow-sm"
                      : "text-stone-700 hover:bg-stone-100/80"
                  }`}
                >
                  <div className="flex items-center gap-2 truncate">
                    <TableIcon className={`h-4 w-4 ${active ? "text-white" : "text-stone-400"}`} />
                    <span className="truncate">{e.table || e.alias}</span>
                  </div>
                  <span className={`text-[11px] ${active ? "text-stone-300" : "text-stone-400"}`}>
                    {e.columns?.length || 0} cols
                  </span>
                </button>
              );
            })}
          </div>

          {/* Metrics section */}
          {dataset.metrics && dataset.metrics.length > 0 && (
            <div className="mt-6 border-t border-stone-200 pt-4">
              <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-stone-400">
                Pre-defined Metrics
              </div>
              <div className="space-y-2">
                {dataset.metrics.map((m) => (
                  <div key={m.name} className="rounded-lg border border-stone-200/80 bg-white p-2 text-xs">
                    <div className="font-semibold text-stone-800">{m.name}</div>
                    <code className="mt-0.5 block font-mono text-[11px] text-stone-500 truncate">
                      {m.formula}
                    </code>
                    {m.description && (
                      <p className="mt-1 text-[11px] text-stone-400">{m.description}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </aside>

        {/* Selected Table Details */}
        <section className="flex-1 overflow-y-auto p-8">
          {activeEntity ? (
            <div className="max-w-4xl space-y-6">
              {/* Header card */}
              <div className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-lg font-bold text-stone-900">
                      Table: <code className="font-mono text-stone-800">{activeEntity.table}</code>
                    </h3>
                    <p className="mt-1 text-sm text-stone-600">
                      {activeEntity.description || `One record per row in ${activeEntity.table}.`}
                    </p>
                  </div>
                  <button
                    onClick={() =>
                      onAskQuestion(`Show me sample records from the ${activeEntity.table} table`)
                    }
                    className="flex items-center gap-1.5 rounded-lg bg-stone-900 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-stone-800"
                  >
                    <SparkleIcon className="h-3.5 w-3.5" />
                    Query this table
                  </button>
                </div>

                {activeEntity.primary_key && activeEntity.primary_key.length > 0 && (
                  <div className="mt-3 flex items-center gap-2 text-xs text-stone-500">
                    <KeyIcon className="h-3.5 w-3.5 text-amber-500" />
                    <span>Primary Key:</span>
                    <span className="font-mono font-medium text-stone-700">
                      [{activeEntity.primary_key.join(", ")}]
                    </span>
                  </div>
                )}
              </div>

              {/* Columns Table */}
              <div className="rounded-xl border border-stone-200 bg-white shadow-sm overflow-hidden">
                <div className="border-b border-stone-200 bg-stone-50/70 px-6 py-3">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-stone-500">
                    Columns ({activeEntity.columns?.length || 0})
                  </h4>
                </div>
                <div className="divide-y divide-stone-100">
                  {activeEntity.columns?.map((col) => {
                    const badgeClass = TYPE_STYLES[col.type] || TYPE_STYLES.text;
                    const isPk = activeEntity.primary_key?.includes(col.name);
                    return (
                      <div key={col.name} className="flex flex-col gap-1.5 p-4 sm:flex-row sm:items-start sm:justify-between hover:bg-stone-50/50">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-sm font-semibold text-stone-900">
                              {col.name}
                            </span>
                            {isPk && (
                              <span className="inline-flex items-center gap-0.5 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 border border-amber-200">
                                PK
                              </span>
                            )}
                            <span
                              className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${badgeClass}`}
                            >
                              {col.type}
                            </span>
                          </div>
                          {col.description && (
                            <p className="text-xs text-stone-600">{col.description}</p>
                          )}
                          {col.synonyms && col.synonyms.length > 0 && (
                            <div className="flex items-center gap-1 text-[11px] text-stone-400">
                              <span>Synonyms:</span>
                              <span className="italic">{col.synonyms.join(", ")}</span>
                            </div>
                          )}
                        </div>

                        {/* Allowed / sample categorical values */}
                        {col.values && col.values.length > 0 && (
                          <div className="mt-2 sm:mt-0 flex flex-wrap gap-1 max-w-xs justify-end">
                            {col.values.slice(0, 10).map((v) => (
                              <span
                                key={v}
                                className="rounded bg-stone-100 px-1.5 py-0.5 font-mono text-[10px] text-stone-600"
                              >
                                {v}
                              </span>
                            ))}
                            {col.values.length > 10 && (
                              <span className="text-[10px] text-stone-400">
                                +{col.values.length - 10} more
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Sample Questions for this dataset */}
              {dataset.sample_questions && dataset.sample_questions.length > 0 && (
                <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
                  <div className="mb-2 text-xs font-bold uppercase tracking-wider text-stone-500">
                    Suggested Questions for this Dataset
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {dataset.sample_questions.map((q) => (
                      <button
                        key={q}
                        onClick={() => onAskQuestion(q)}
                        className="rounded-lg border border-stone-200 bg-stone-50 px-3 py-1.5 text-xs text-stone-700 transition hover:border-emerald-500 hover:bg-emerald-50 hover:text-emerald-800"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-stone-400">Select a table to view its schema.</div>
          )}
        </section>
      </div>
    </div>
  );
}
