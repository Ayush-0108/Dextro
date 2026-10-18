import { useState } from "react";
import type { Dataset, Health } from "../types";
import * as api from "../api";

const DOT = { ok: "bg-ok", warn: "bg-warn", bad: "bg-bad" } as const;

export default function Sidebar(p: {
  datasets: Dataset[]; dataset: string; onDataset: (id: string) => void; health: Health | null;
  role: "analyst" | "restricted"; onRole: (r: "analyst" | "restricted") => void; onNew: () => void;
  history: string[]; onSelectHistory: (q: string) => void; onClearHistory: () => void;
  onUploadSuccess: (datasets: Dataset[], newId: string) => void;
}) {
  const ds = p.datasets.find((d) => d.id === p.dataset);
  const [demo, setDemo] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [uploadSuccess, setUploadSuccess] = useState("");

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setUploadError("");
    setUploadSuccess("");
    try {
      const res = await api.uploadDataset(file, name, title);
      setUploadSuccess(`Loaded ${res.rows} rows into ${res.title}!`);
      p.onUploadSuccess(res.datasets, res.id);
      setTimeout(() => {
        setUploadOpen(false);
        setFile(null);
        setName("");
        setTitle("");
        setUploadSuccess("");
      }, 1200);
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  };

  return (
    <aside className="flex h-full w-80 flex-none flex-col gap-4 overflow-y-auto border-r border-sand-line bg-sand-100 px-5 py-6">
      <div>
        <div className="flex items-center gap-2"><span className="grid h-8 w-8 place-items-center rounded-lg bg-ink text-sm font-bold text-sand-50">N</span>
          <span className="text-xl font-bold tracking-tight">Nexora</span></div>
        <p className="mt-1 text-xs text-ink-muted">Verified AI data analyst · by Dextro</p>
      </div>

      <section>
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-ink-muted">System status · live</div>
        {p.health ? Object.entries(p.health).map(([sname, h]) => (
          <div key={sname} className="mb-2 rounded-lg border border-sand-line bg-white px-3 py-2 shadow-card">
            <div className="flex items-center gap-2 text-sm"><span className={`h-2 w-2 rounded-full ${DOT[h.state]}`} />
              <b className="capitalize">{sname}</b><span className="text-ink-body">{h.label}</span></div>
            <div className="mt-0.5 pl-4 text-xs text-ink-muted">
              {h.warehouse ? `${h.warehouse} · ${h.region} · v${h.version}` : h.detail}</div>
          </div>)) : <p className="text-xs text-ink-muted">Checking…</p>}
        <a href="https://github.com/ZERODAY-2026/Dextro/actions/workflows/tests.yml" target="_blank" rel="noreferrer">
          <img alt="tests (live CI status)" src="https://github.com/ZERODAY-2026/Dextro/actions/workflows/tests.yml/badge.svg" className="mt-1 h-5" /></a>
      </section>

      <section>
        <div className="mb-1 flex items-center justify-between">
          <label htmlFor="dataset" className="text-[11px] font-semibold uppercase tracking-wide text-ink-muted">Dataset</label>
          <button onClick={() => setUploadOpen(true)} className="text-xs font-semibold text-ok hover:underline">
            + Upload CSV
          </button>
        </div>
        <select id="dataset" value={p.dataset} onChange={(e) => p.onDataset(e.target.value)}
          className="w-full rounded-lg border border-sand-line bg-white px-3 py-2 text-sm shadow-card focus:border-ok focus:outline-none">
          {p.datasets.map((d) => <option key={d.id} value={d.id}>{d.title} · {d.tables} tables</option>)}
        </select>
        <p className="mt-1.5 text-xs text-ink-muted">{ds?.coverage}</p>
        <p className="mt-1 text-[11px] text-ink-muted">Same code, different semantic model (config/datasets/*.yaml).</p>
      </section>

      {/* Query History */}
      {p.history.length > 0 && (
        <section className="rounded-lg border border-sand-line bg-white p-3 shadow-card">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-muted">Query history ({p.history.length})</span>
            <button onClick={p.onClearHistory} className="text-[10px] text-ink-muted hover:text-bad">Clear</button>
          </div>
          <div className="max-h-36 space-y-1 overflow-y-auto">
            {p.history.map((q, i) => (
              <button key={i} onClick={() => p.onSelectHistory(q)}
                title={q}
                className="w-full truncate rounded px-2 py-1 text-left text-xs text-ink-body hover:bg-sand-100 hover:text-ink">
                • {q}
              </button>
            ))}
          </div>
        </section>
      )}

      <section>
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-muted">Answer as</div>
        <div className="grid grid-cols-2 rounded-lg border border-sand-line bg-white p-1 shadow-card" role="radiogroup">
          {(["analyst", "restricted"] as const).map((r) => (
            <button key={r} role="radio" aria-checked={p.role === r} onClick={() => p.onRole(r)}
              className={`rounded-md px-2 py-1.5 text-sm font-medium capitalize ${p.role === r ? "bg-ink text-sand-50" : "text-ink-body hover:bg-sand-100"}`}>{r}</button>))}
        </div>
        <p className="mt-1.5 text-xs text-ink-muted">{p.role === "restricted" ? "Personal data (phones, balances, emails) is masked by Snowflake dynamic masking policies." : "Full read-only access (SELECT only)."}</p>
      </section>

      <section className="rounded-lg border border-sand-line bg-white shadow-card">
        <button onClick={() => setDemo(!demo)} className="flex w-full items-center justify-between px-3 py-2 text-sm font-semibold" aria-expanded={demo}>
          ⚡ Live data-change demo <span className={`transition-transform ${demo ? "rotate-180" : ""}`}>⌄</span></button>
        {demo && <ol className="list-decimal space-y-1 border-t border-sand-line px-3 py-2 pl-7 text-xs text-ink-body">
          <li>Ask: <i>Which customer generated the most revenue from orders placed in July 1998?</i></li>
          <li>In Snowsight run STEP 1–2 of <code className="font-mono">snowflake/02_demo_data_change.sql</code> (adds one large order).</li>
          <li>Ask again: a new answer with a new Snowflake query id.</li>
          <li>STEP 4: Time Travel before vs after · STEP 5 reverts.</li>
          <li className="list-none -ml-4 pt-1 text-ink-muted">Nexora never writes: its role is SELECT-only, so the change is made in Snowsight.</li>
        </ol>}
      </section>

      <button onClick={p.onNew} className="mt-auto rounded-lg border border-sand-line bg-white px-3 py-2 text-sm font-medium shadow-card hover:border-ok">New conversation</button>

      {/* Upload Modal */}
      {uploadOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-sand-line bg-white p-6 shadow-float">
            <h3 className="text-lg font-bold text-ink">Upload New Dataset (CSV)</h3>
            <p className="mt-1 text-xs text-ink-muted">
              Upload any tabular CSV file. DataMind will automatically load it into Snowflake/DuckDB and draft a semantic model in seconds.
            </p>
            <form onSubmit={handleUpload} className="mt-4 space-y-3">
              <div>
                <label className="block text-xs font-semibold text-ink-body">CSV File</label>
                <input type="file" accept=".csv" required onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) {
                    setFile(f);
                    const base = f.name.replace(/\.csv$/i, "");
                    if (!name) setName(base.toLowerCase().replace(/[^a-z0-9_]/g, "_"));
                    if (!title) setTitle(base.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()));
                  }
                }} className="mt-1 w-full text-xs text-ink-muted file:mr-3 file:rounded-lg file:border-0 file:bg-sand-100 file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-ink hover:file:bg-sand-200" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-ink-body">Dataset Title</label>
                <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Superstore Sales"
                  className="mt-1 w-full rounded-lg border border-sand-line px-3 py-2 text-xs focus:border-ok focus:outline-none" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-ink-body">Identifier (slug)</label>
                <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. sales"
                  className="mt-1 w-full rounded-lg border border-sand-line px-3 py-2 text-xs font-mono focus:border-ok focus:outline-none" />
              </div>

              {uploadError && <div className="rounded-lg bg-bad-soft p-2 text-xs text-bad">{uploadError}</div>}
              {uploadSuccess && <div className="rounded-lg bg-ok-soft p-2 text-xs text-ok">{uploadSuccess}</div>}

              <div className="mt-5 flex justify-end gap-2">
                <button type="button" onClick={() => setUploadOpen(false)} disabled={uploading}
                  className="rounded-lg border border-sand-line px-3 py-1.5 text-xs font-medium text-ink-body hover:bg-sand-100">Cancel</button>
                <button type="submit" disabled={uploading || !file}
                  className="rounded-lg bg-ink px-4 py-1.5 text-xs font-semibold text-sand-50 hover:bg-ink-muted disabled:opacity-40">
                  {uploading ? "Uploading & Drafting..." : "Upload & Build Model"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </aside>
  );
}
