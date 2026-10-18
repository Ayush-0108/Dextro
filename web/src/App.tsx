import { useEffect, useRef, useState } from "react";
import * as api from "./api";
import Sidebar from "./components/Sidebar";
import Evidence from "./components/Tabs";
import Receipt from "./components/Receipt";
import type { Answer, Dataset, Health } from "./types";

type Turn = { question: string; answer?: Answer; error?: string };

export default function App() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [dataset, setDataset] = useState("");
  const [role, setRole] = useState<"analyst" | "restricted">("analyst");
  const [health, setHealth] = useState<Health | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [loadError, setLoadError] = useState("");
  const [historyList, setHistoryList] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem("datamind_query_history") || "[]"); } catch { return []; }
  });
  const bottom = useRef<HTMLDivElement>(null);

  const saveToHistory = (q: string) => {
    setHistoryList((prev) => {
      const next = [q, ...prev.filter((x) => x !== q)].slice(0, 25);
      try { localStorage.setItem("datamind_query_history", JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
  };

  const clearHistory = () => {
    setHistoryList([]);
    try { localStorage.removeItem("datamind_query_history"); } catch { /* ignore */ }
  };

  useEffect(() => {
    api.getDatasets().then((d) => { setDatasets(d.datasets); setDataset(d.default); })
      .catch((e) => setLoadError(String(e)));
  }, []);
  useEffect(() => {
    if (!dataset) return;
    setHealth(null);
    api.getHealth(dataset).then(setHealth).catch((e) => setHealth({ server: { state: "bad", label: "API error", detail: String(e) } }));
  }, [dataset]);
  useEffect(() => {
    if (!busy) return;
    const t0 = Date.now(), id = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 500);
    return () => clearInterval(id);
  }, [busy]);
  // braces matter: newer browsers return a Promise from scrollIntoView, and an effect must not return one
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [turns, busy]);

  const submit = async (q: string) => {
    const question = q.trim();
    if (!question || busy) return;
    saveToHistory(question);
    setInput(""); setBusy(true); setElapsed(0);
    const history = turns.filter((t) => t.answer && ["answered", "empty"].includes(t.answer.status)).map((t) => t.answer!.history_entry);
    setTurns((ts) => [...ts, { question }]);
    try {
      const answer = await api.ask(question, dataset, role, history);
      setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? { ...t, answer } : t)));
    } catch (e) {
      setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? { ...t, error: String(e) } : t)));
    } finally { setBusy(false); }
  };

  const ds = datasets.find((d) => d.id === dataset);
  if (loadError) return <div className="p-10 text-bad">Can't reach the Nexora API ({loadError}). Start it with <code className="font-mono">uvicorn api.server:app --port 8000</code>.</div>;

  return (
    <div className="flex h-screen">
      <Sidebar datasets={datasets} dataset={dataset} onDataset={(id) => { setDataset(id); setTurns([]); }}
        health={health} role={role} onRole={setRole} onNew={() => setTurns([])}
        history={historyList} onSelectHistory={(q) => submit(q)} onClearHistory={clearHistory}
        onUploadSuccess={(newDatasets, newId) => { setDatasets(newDatasets); setDataset(newId); setTurns([]); }} />
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-5xl px-8 pb-48 pt-8">
            <h1 className="text-2xl font-bold tracking-tight">Ask your data</h1>
            <p className="mt-1 text-sm text-ink-muted">Every answer is computed by SQL in Snowflake at question time, cross-checked, and shown with the evidence behind it.</p>
            {turns.map((t, i) => (
              <section key={i} className="mt-8">
                <div className="mb-3 ml-auto w-fit max-w-[80%] rounded-2xl rounded-br-sm bg-ink px-4 py-2.5 text-sm text-sand-50">{t.question}</div>
                {t.answer && <><Receipt a={t.answer} onInterpret={submit} />{t.answer.chosen && t.answer.result && <Evidence a={t.answer} health={health} />}</>}
                {t.error && <div className="rounded-xl border border-bad-line bg-bad-soft p-4 text-sm text-bad">Request failed: {t.error}</div>}
                {!t.answer && !t.error && (
                  <div className="flex items-center gap-3 rounded-xl border border-sand-line bg-white p-4 text-sm text-ink-body shadow-card" role="status" aria-live="polite">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-sand-line border-t-ok" />
                    Understanding the question, writing two independent queries, running them in Snowflake, cross-checking… <b>{elapsed}s</b>
                    <span className="text-xs text-ink-muted">(Gemma on a laptop: up to a few minutes)</span>
                  </div>)}
              </section>))}
            <div ref={bottom} />
          </div>
        </div>
        <div className="pointer-events-none absolute bottom-0 left-80 right-0 bg-gradient-to-t from-sand-50 via-sand-50 to-transparent pb-6 pt-10">
          <div className="pointer-events-auto mx-auto max-w-4xl px-8">
            <form onSubmit={(e) => { e.preventDefault(); submit(input); }}
              className="flex items-center gap-2 rounded-2xl border border-sand-line bg-white p-2 shadow-float focus-within:border-ok">
              <input value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} aria-label="Your question"
                placeholder={ds?.sample_questions[0] ? `e.g. ${ds.sample_questions[0]}` : "Ask a question about your data"}
                className="flex-1 bg-transparent px-3 py-2 text-[15px] outline-none placeholder:text-ink-muted" />
              <button disabled={busy || !input.trim()} className="rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-sand-50 disabled:opacity-40">{busy ? "Working…" : "Ask"}</button>
            </form>
            <div className="mt-2 flex flex-wrap gap-2">
              {(ds?.sample_questions ?? []).slice(0, 4).map((q) => (
                <button key={q} onClick={() => submit(q)} disabled={busy}
                  className="rounded-full border border-sand-line bg-white px-3 py-1 text-xs text-ink-body shadow-card hover:border-ok hover:text-ok disabled:opacity-40">{q}</button>))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
