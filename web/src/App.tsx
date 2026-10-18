import { useEffect, useRef, useState } from "react";
import * as api from "./api";
import Sidebar from "./components/Sidebar";
import Evidence from "./components/Tabs";
import Receipt from "./components/Receipt";
import DataExplorer from "./components/DataExplorer";
import SavedAnalyses, { type SavedItem } from "./components/SavedAnalyses";
import SettingsModal from "./components/SettingsModal";
import UploadModal from "./components/UploadModal";
import type { Answer, Dataset, Health } from "./types";
import {
  PaperclipIcon,
  DatabaseIcon,
  ArrowUpIcon,
  BookmarkIcon,
  CheckIcon,
} from "./components/icons";

interface Turn {
  question: string;
  answer?: Answer;
  error?: string;
  saved?: boolean;
}

export default function App() {
  const [currentView, setCurrentView] = useState<"ask" | "explorer" | "saved">("ask");
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [dataset, setDataset] = useState("");
  const [role, setRole] = useState<"analyst" | "restricted">("analyst");
  const [health, setHealth] = useState<Health | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [loadError, setLoadError] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [schemaMenuOpen, setSchemaMenuOpen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadNotice, setUploadNotice] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const schemaMenuRef = useRef<HTMLDivElement>(null);

  // History state persisted in localStorage
  const [historyList, setHistoryList] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem("datamind_query_history") || "[]");
    } catch {
      return [];
    }
  });

  // Saved analyses state persisted in localStorage
  const [savedList, setSavedList] = useState<SavedItem[]>(() => {
    try {
      return JSON.parse(localStorage.getItem("datamind_saved_analyses") || "[]");
    } catch {
      return [];
    }
  });

  const saveToHistory = (q: string) => {
    setHistoryList((prev) => {
      const next = [q, ...prev.filter((x) => x !== q)].slice(0, 30);
      try {
        localStorage.setItem("datamind_query_history", JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  const clearHistory = () => {
    setHistoryList([]);
    try {
      localStorage.removeItem("datamind_query_history");
    } catch {
      /* ignore */
    }
  };

  const toggleSaveAnalysis = (q: string, a?: Answer) => {
    const existing = savedList.find((s) => s.question === q);
    let next: SavedItem[];
    if (existing) {
      next = savedList.filter((s) => s.question !== q);
    } else {
      const dsObj = datasets.find((d) => d.id === dataset);
      next = [
        {
          id: a?.answer_id || String(Date.now()),
          question: q,
          datasetTitle: dsObj?.title || dataset || "Dataset",
          timestamp: Date.now(),
        },
        ...savedList,
      ];
    }
    setSavedList(next);
    try {
      localStorage.setItem("datamind_saved_analyses", JSON.stringify(next));
    } catch {
      /* ignore */
    }
  };

  // Initial load
  useEffect(() => {
    api
      .getDatasets()
      .then((d) => {
        setDatasets(d.datasets);
        setDataset(d.default);
      })
      .catch((e) => setLoadError(String(e)));
  }, []);

  // Health check on dataset switch
  useEffect(() => {
    if (!dataset) return;
    setHealth(null);
    api
      .getHealth(dataset)
      .then(setHealth)
      .catch((e) =>
        setHealth({
          server: { state: "bad", label: "API error", detail: String(e) },
        })
      );
  }, [dataset]);

  // Elapsed query timer
  useEffect(() => {
    if (!busy) return;
    const t0 = Date.now();
    const id = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 400);
    return () => clearInterval(id);
  }, [busy]);

  // Auto-scroll on new turns
  useEffect(() => {
    if (currentView === "ask") {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [turns, busy, currentView]);

  // Close schema dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (schemaMenuRef.current && !schemaMenuRef.current.contains(event.target as Node)) {
        setSchemaMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const submit = async (q: string) => {
    const question = q.trim();
    if (!question || busy) return;
    saveToHistory(question);
    setInput("");
    setBusy(true);
    setElapsed(0);
    setCurrentView("ask");

    const history = turns
      .filter((t) => t.answer && ["answered", "empty"].includes(t.answer.status))
      .map((t) => t.answer!.history_entry);

    setTurns((ts) => [...ts, { question }]);

    try {
      const answer = await api.ask(question, dataset, role, history);
      setTurns((ts) =>
        ts.map((t, i) => (i === ts.length - 1 ? { ...t, answer } : t))
      );
    } catch (e) {
      setTurns((ts) =>
        ts.map((t, i) => (i === ts.length - 1 ? { ...t, error: String(e) } : t))
      );
    } finally {
      setBusy(false);
    }
  };

  const handleFileUpload = async (file: File) => {
    setUploadNotice(`Uploading ${file.name} & drafting semantic model...`);
    try {
      const base = file.name.replace(/\.[^/.]+$/, "");
      const res = await api.uploadDataset(
        file,
        base.toLowerCase().replace(/[^a-z0-9_]/g, "_"),
        base.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
      );
      setDatasets(res.datasets);
      setDataset(res.id);
      setTurns([]);
      setUploadNotice(`✓ Loaded ${res.rows} rows into "${res.title}"! Ask any question.`);
      setTimeout(() => setUploadNotice(null), 4000);
    } catch (err: unknown) {
      setUploadNotice(`Error: ${err instanceof Error ? err.message : String(err)}`);
      setTimeout(() => setUploadNotice(null), 4000);
    }
  };

  const activeDatasetObj = datasets.find((d) => d.id === dataset);

  if (loadError) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#FAFAF9] p-8 text-stone-700">
        <div className="max-w-md rounded-2xl border border-red-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-bold text-red-600">API Connection Error</h2>
          <p className="mt-2 text-xs text-stone-600">{loadError}</p>
          <p className="mt-3 text-xs text-stone-400">
            Make sure the DataMind server is running on <code className="font-mono">localhost:8000</code>.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex h-screen overflow-hidden bg-[#FAFAF9]"
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) {
          setIsDragging(false);
        }
      }}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragging(false);
        const f = e.dataTransfer.files?.[0];
        if (f) handleFileUpload(f);
      }}
    >
      {/* Hidden file input for paperclip */}
      <input
        type="file"
        ref={fileInputRef}
        accept=".csv,.xlsx,.json"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handleFileUpload(f);
        }}
      />

      {/* Drag & Drop full-screen overlay */}
      {isDragging && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-900/40 backdrop-blur-sm pointer-events-none">
          <div className="rounded-2xl border-2 border-dashed border-white bg-stone-900/80 p-8 text-center text-white shadow-2xl">
            <PaperclipIcon className="mx-auto h-12 w-12 text-white/80 animate-bounce" />
            <h3 className="mt-4 text-xl font-bold">Drop your file here</h3>
            <p className="mt-1 text-sm text-stone-300">
              CSV, XLSX, or JSON will be automatically loaded into Snowflake/DuckDB.
            </p>
          </div>
        </div>
      )}

      {/* Left Sidebar */}
      <Sidebar
        currentView={currentView}
        onSelectView={setCurrentView}
        health={health}
        onNew={() => {
          setTurns([]);
          setCurrentView("ask");
        }}
        history={historyList}
        onSelectHistory={(q) => {
          setCurrentView("ask");
          submit(q);
        }}
        onClearHistory={clearHistory}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenUpload={() => setUploadModalOpen(true)}
      />

      {/* Main Content Area */}
      <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Upload feedback toast */}
        {uploadNotice && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 z-40 rounded-xl border border-stone-200 bg-white px-4 py-2 text-xs font-semibold text-stone-800 shadow-float">
            {uploadNotice}
          </div>
        )}

        {/* VIEW 1: Data Explorer */}
        {currentView === "explorer" && (
          <DataExplorer
            dataset={activeDatasetObj}
            onAskQuestion={(q) => {
              setCurrentView("ask");
              setInput(q);
            }}
            onOpenUpload={() => setUploadModalOpen(true)}
          />
        )}

        {/* VIEW 2: Saved Analyses */}
        {currentView === "saved" && (
          <SavedAnalyses
            saved={savedList}
            onRun={(q) => {
              setCurrentView("ask");
              submit(q);
            }}
            onRemove={(id) => {
              const next = savedList.filter((s) => s.id !== id);
              setSavedList(next);
              try {
                localStorage.setItem("datamind_saved_analyses", JSON.stringify(next));
              } catch {
                /* ignore */
              }
            }}
          />
        )}

        {/* VIEW 3: Ask Data */}
        {currentView === "ask" && (
          <div className="flex h-full flex-1 flex-col overflow-hidden">
            {/* Top Bar for turns view */}
            {turns.length > 0 && (
              <header className="flex h-14 flex-none items-center justify-between border-b border-stone-200/80 bg-white/80 px-6 backdrop-blur-sm">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-md bg-stone-100 text-stone-700">
                    <DatabaseIcon className="h-3.5 w-3.5" />
                  </span>
                  <span className="text-xs font-bold text-stone-800">
                    {activeDatasetObj?.title || dataset}
                  </span>
                  <span className="rounded-full bg-stone-100 px-2 py-0.5 text-[10px] font-semibold text-stone-500">
                    Role: {role === "analyst" ? "DATAMIND_AGENT" : "DATAMIND_RESTRICTED (PII Masked)"}
                  </span>
                </div>
                <button
                  onClick={() => setTurns([])}
                  className="rounded-lg border border-stone-200 bg-white px-2.5 py-1 text-xs font-medium text-stone-600 shadow-sm hover:bg-stone-50"
                >
                  Clear Chat
                </button>
              </header>
            )}

            {/* Content Area */}
            <div className="flex-1 overflow-y-auto">
              {turns.length === 0 ? (
                /* Hero State (Matching user screenshot) */
                <div className="flex min-h-full flex-col items-center justify-center px-4 py-12">
                  {/* Headings */}
                  <div className="text-center">
                    <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-stone-900">
                      Bring your data to life.
                    </h1>
                    <p className="mt-2 text-sm sm:text-base text-stone-500">
                      Attach a dataset and ask questions in natural language.
                    </p>
                  </div>

                  {/* Composer Card */}
                  <div className="mt-8 w-full max-w-2xl rounded-2xl border border-stone-200/90 bg-white p-4 shadow-sm transition-all focus-within:border-stone-300 focus-within:shadow-md">
                    <textarea
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          submit(input);
                        }
                      }}
                      disabled={busy}
                      placeholder="Ask anything about your data..."
                      rows={3}
                      className="w-full resize-none bg-transparent text-sm text-stone-800 placeholder:text-stone-400 focus:outline-none"
                    />

                    {/* Bottom Action Row inside composer */}
                    <div className="mt-2 flex items-center justify-between border-t border-stone-100 pt-3">
                      {/* Left: Attachment & Schema Pill */}
                      <div className="flex items-center gap-2">
                        {/* Paperclip */}
                        <button
                          type="button"
                          onClick={() => setUploadModalOpen(true)}
                          title="Upload CSV Dataset"
                          className="flex h-7 w-7 items-center justify-center rounded-full text-stone-400 hover:bg-stone-100 hover:text-stone-700 transition"
                        >
                          <PaperclipIcon className="h-4 w-4" />
                        </button>

                        {/* Schema Pill with Dropdown */}
                        <div className="relative" ref={schemaMenuRef}>
                          <button
                            type="button"
                            onClick={() => setSchemaMenuOpen(!schemaMenuOpen)}
                            className="flex items-center gap-1.5 rounded-full border border-stone-200 bg-stone-50/70 px-2.5 py-1 text-xs font-medium text-stone-700 hover:bg-stone-100/80 transition"
                          >
                            <DatabaseIcon className="h-3.5 w-3.5 text-stone-500" />
                            <span className="truncate max-w-[140px]">
                              {activeDatasetObj ? activeDatasetObj.title.split(" (")[0] : "Sample Schema"}
                            </span>
                          </button>

                          {/* Dataset Picker Dropdown */}
                          {schemaMenuOpen && (
                            <div className="absolute left-0 bottom-full mb-1.5 z-30 w-72 rounded-xl border border-stone-200 bg-white p-2 shadow-float">
                              <div className="px-2 py-1 text-[11px] font-bold uppercase tracking-wider text-stone-400">
                                Select Dataset
                              </div>
                              <div className="mt-1 space-y-0.5 max-h-56 overflow-y-auto">
                                {datasets.map((d) => (
                                  <button
                                    key={d.id}
                                    onClick={() => {
                                      setDataset(d.id);
                                      setSchemaMenuOpen(false);
                                    }}
                                    className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs transition ${
                                      d.id === dataset
                                        ? "bg-stone-900 text-white font-medium"
                                        : "text-stone-700 hover:bg-stone-100"
                                    }`}
                                  >
                                    <div className="truncate">
                                      <div className="truncate font-semibold">{d.title}</div>
                                      <div className={`truncate text-[10px] ${d.id === dataset ? "text-stone-300" : "text-stone-400"}`}>
                                        {d.tables} tables
                                      </div>
                                    </div>
                                    {d.id === dataset && <CheckIcon className="h-3.5 w-3.5 text-white flex-none" />}
                                  </button>
                                ))}
                              </div>
                              <div className="mt-2 border-t border-stone-100 pt-1.5">
                                <button
                                  onClick={() => {
                                    setSchemaMenuOpen(false);
                                    setUploadModalOpen(true);
                                  }}
                                  className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs font-semibold text-emerald-600 hover:bg-emerald-50 transition"
                                >
                                  <span>+</span>
                                  <span>Upload New Dataset (CSV)</span>
                                </button>
                              </div>
                            </div>
                          )}
                        </div>

                        {/* Direct Upload Shortcut Button */}
                        <button
                          type="button"
                          onClick={() => setUploadModalOpen(true)}
                          className="text-[11px] font-semibold text-emerald-600 hover:text-emerald-700 hover:underline transition ml-1"
                        >
                          + Upload CSV
                        </button>
                      </div>

                      {/* Right: Enter hint & Send button */}
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] text-stone-400 select-none">Enter to send</span>
                        <button
                          type="button"
                          onClick={() => submit(input)}
                          disabled={busy || !input.trim()}
                          className="flex h-7 w-7 items-center justify-center rounded-full bg-stone-900 text-white shadow-sm transition hover:bg-stone-800 disabled:opacity-30 disabled:pointer-events-none"
                        >
                          <ArrowUpIcon className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Helper Text below composer */}
                  <p className="mt-4 text-center text-xs text-stone-400 max-w-lg">
                    Drag and drop a CSV, XLSX, or JSON file directly onto the composer, or click the paperclip icon.
                  </p>

                  {/* Sample Questions Chips */}
                  {activeDatasetObj?.sample_questions && activeDatasetObj.sample_questions.length > 0 && (
                    <div className="mt-6 flex flex-wrap justify-center gap-2 max-w-2xl">
                      {activeDatasetObj.sample_questions.slice(0, 4).map((q) => (
                        <button
                          key={q}
                          onClick={() => submit(q)}
                          disabled={busy}
                          className="rounded-full border border-stone-200/90 bg-white px-3.5 py-1.5 text-xs text-stone-600 shadow-[0_1px_2px_rgba(0,0,0,0.03)] hover:border-stone-400 hover:text-stone-900 transition disabled:opacity-40"
                        >
                          {q}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                /* Turns / Results View */
                <div className="mx-auto max-w-5xl px-6 py-6 space-y-6 pb-48">
                  {turns.map((t, i) => {
                    const isSaved = savedList.some((s) => s.question === t.question);
                    return (
                      <section key={i} className="space-y-3">
                        {/* User Question */}
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => toggleSaveAnalysis(t.question, t.answer)}
                            title={isSaved ? "Saved to Analyses" : "Save to Analyses"}
                            className={`rounded-lg p-1.5 text-xs transition ${
                              isSaved
                                ? "bg-amber-50 text-amber-600 border border-amber-200"
                                : "text-stone-400 hover:text-stone-700 hover:bg-stone-100"
                            }`}
                          >
                            <BookmarkIcon className="h-3.5 w-3.5" />
                          </button>
                          <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-stone-900 px-4 py-2.5 text-sm text-stone-100 shadow-sm">
                            {t.question}
                          </div>
                        </div>

                        {/* Assistant Answer Receipt */}
                        {t.answer && (
                          <div className="space-y-3">
                            <Receipt a={t.answer} onInterpret={submit} />
                            {t.answer.chosen && t.answer.result && (
                              <Evidence a={t.answer} health={health} />
                            )}
                          </div>
                        )}

                        {/* Error Message */}
                        {t.error && (
                          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-600">
                            Request failed: {t.error}
                          </div>
                        )}

                        {/* Progress Spinner */}
                        {!t.answer && !t.error && (
                          <div
                            className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white p-4 text-xs text-stone-700 shadow-card"
                            role="status"
                            aria-live="polite"
                          >
                            <span className="h-4 w-4 animate-spin rounded-full border-2 border-stone-200 border-t-emerald-600" />
                            <span>
                              Understanding question, generating dual SQL candidates, running Snowflake read-only query, verifying cells…{" "}
                              <b>{elapsed}s</b>
                            </span>
                            <span className="text-[11px] text-stone-400">
                              (Gemma on local Ollama)
                            </span>
                          </div>
                        )}
                      </section>
                    );
                  })}
                  <div ref={bottomRef} />
                </div>
              )}
            </div>

            {/* Bottom Floating Composer when turns are present */}
            {turns.length > 0 && (
              <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-[#FAFAF9] via-[#FAFAF9]/90 to-transparent pb-6 pt-10">
                <div className="mx-auto max-w-3xl px-6">
                  <div className="rounded-2xl border border-stone-200/90 bg-white p-3 shadow-float">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setUploadModalOpen(true)}
                        title="Upload CSV Dataset"
                        className="rounded-lg p-1.5 text-stone-400 hover:bg-stone-100 hover:text-stone-700 transition"
                      >
                        <PaperclipIcon className="h-4 w-4" />
                      </button>
                      <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            submit(input);
                          }
                        }}
                        disabled={busy}
                        placeholder={
                          activeDatasetObj?.sample_questions[0]
                            ? `Ask follow-up (e.g. ${activeDatasetObj.sample_questions[0]})`
                            : "Ask a follow-up question..."
                        }
                        className="flex-1 bg-transparent px-2 text-sm text-stone-800 placeholder:text-stone-400 focus:outline-none"
                      />
                      <button
                        type="button"
                        onClick={() => submit(input)}
                        disabled={busy || !input.trim()}
                        className="flex h-7 w-7 items-center justify-center rounded-full bg-stone-900 text-white shadow-sm transition hover:bg-stone-800 disabled:opacity-30 disabled:pointer-events-none"
                      >
                        <ArrowUpIcon className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Settings & System Health Modal */}
      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        health={health}
        role={role}
        onRole={setRole}
      />

      {/* Upload CSV Dataset Modal */}
      <UploadModal
        open={uploadModalOpen}
        onClose={() => setUploadModalOpen(false)}
        onSuccess={(newDatasets, newId) => {
          setDatasets(newDatasets);
          setDataset(newId);
          setTurns([]);
          setCurrentView("explorer");
          setUploadNotice("✓ Dataset loaded successfully! Table schema and columns are ready below.");
          setTimeout(() => setUploadNotice(null), 5000);
        }}
      />
    </div>
  );
}
