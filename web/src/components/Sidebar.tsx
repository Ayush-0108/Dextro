import { useState } from "react";
import type { Dataset, Health } from "../types";

const DOT = { ok: "bg-ok", warn: "bg-warn", bad: "bg-bad" } as const;

export default function Sidebar(p: {
  datasets: Dataset[]; dataset: string; onDataset: (id: string) => void; health: Health | null;
  role: "analyst" | "restricted"; onRole: (r: "analyst" | "restricted") => void; onNew: () => void;
}) {
  const ds = p.datasets.find((d) => d.id === p.dataset);
  const [demo, setDemo] = useState(false);
  return (
    <aside className="flex h-full w-80 flex-none flex-col gap-5 overflow-y-auto border-r border-sand-line bg-sand-100 px-5 py-6">
      <div>
        <div className="flex items-center gap-2"><span className="grid h-8 w-8 place-items-center rounded-lg bg-ink text-sm font-bold text-sand-50">N</span>
          <span className="text-xl font-bold tracking-tight">Nexora</span></div>
        <p className="mt-1 text-xs text-ink-muted">Verified AI data analyst · by Dextro</p>
      </div>

      <section>
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-ink-muted">System status · live</div>
        {p.health ? Object.entries(p.health).map(([name, h]) => (
          <div key={name} className="mb-2 rounded-lg border border-sand-line bg-white px-3 py-2 shadow-card">
            <div className="flex items-center gap-2 text-sm"><span className={`h-2 w-2 rounded-full ${DOT[h.state]}`} />
              <b className="capitalize">{name}</b><span className="text-ink-body">{h.label}</span></div>
            <div className="mt-0.5 pl-4 text-xs text-ink-muted">
              {h.warehouse ? `${h.warehouse} · ${h.region} · v${h.version}` : h.detail}</div>
          </div>)) : <p className="text-xs text-ink-muted">Checking…</p>}
        <a href="https://github.com/ZERODAY-2026/Dextro/actions/workflows/tests.yml" target="_blank" rel="noreferrer">
          <img alt="tests (live CI status)" src="https://github.com/ZERODAY-2026/Dextro/actions/workflows/tests.yml/badge.svg" className="mt-1 h-5" /></a>
      </section>

      <section>
        <label htmlFor="dataset" className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-ink-muted">Dataset</label>
        <select id="dataset" value={p.dataset} onChange={(e) => p.onDataset(e.target.value)}
          className="w-full rounded-lg border border-sand-line bg-white px-3 py-2 text-sm shadow-card focus:border-ok focus:outline-none">
          {p.datasets.map((d) => <option key={d.id} value={d.id}>{d.title} · {d.tables} tables</option>)}
        </select>
        <p className="mt-1.5 text-xs text-ink-muted">{ds?.coverage}</p>
        <p className="mt-1 text-[11px] text-ink-muted">Same code, different semantic model (config/datasets/*.yaml).</p>
      </section>

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
    </aside>
  );
}
