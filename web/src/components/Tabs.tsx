import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Answer, Health } from "../types";
import Tower from "./Tower";
import { Card, Pill, fmt } from "./ui";

const TIMEISH = /date|year|month|quarter|week|period/i;
const isNum = (v: unknown) => typeof v === "number";

function Chart({ a }: { a: Answer }) {
  const r = a.result!;
  if (r.rows.length < 2 || r.rows.length > 60 || r.columns.length < 2) return null;
  const numCols = r.columns.filter((_, i) => r.rows.every((row) => row[i] === null || isNum(row[i])));
  const labCols = r.columns.filter((c) => !numCols.includes(c));
  let x: string, y: string;
  if (labCols.length === 1 && numCols.length) [x, y] = [labCols[0], numCols[0]];
  else if (!labCols.length && numCols.length >= 2 && TIMEISH.test(numCols[0])) [x, y] = [numCols[0], numCols[1]];
  else return null;
  const xi = r.columns.indexOf(x), yi = r.columns.indexOf(y);
  const time = TIMEISH.test(x);
  let data = r.rows.map((row) => ({ x: String(row[xi]), y: Number(row[yi]) }));
  if (time) data = [...data].sort((p, q) => (p.x < q.x ? -1 : 1));   // a time axis in time order, whatever the row order
  const axis = { stroke: "#78716C", fontSize: 12 };
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        {time ? (
          <LineChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
            <CartesianGrid stroke="#E7E2D8" vertical={false} /><XAxis dataKey="x" tick={axis} /><YAxis tick={axis} tickFormatter={(v) => fmt(v)} width={90} />
            <Tooltip formatter={(v) => fmt(v)} /><Line type="monotone" dataKey="y" name={y} stroke="#059669" strokeWidth={2.5} dot={{ r: 3 }} />
          </LineChart>
        ) : (
          <BarChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
            <CartesianGrid stroke="#E7E2D8" vertical={false} /><XAxis dataKey="x" tick={axis} interval={0} angle={data.length > 8 ? -30 : 0} textAnchor={data.length > 8 ? "end" : "middle"} height={data.length > 8 ? 60 : 30} />
            <YAxis tick={axis} tickFormatter={(v) => fmt(v)} width={90} /><Tooltip formatter={(v) => fmt(v)} /><Bar dataKey="y" name={y} fill="#059669" radius={[4, 4, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

function DataTab({ a }: { a: Answer }) {
  const r = a.result!;
  const cited = new Set(a.number_checks.filter((n) => n.cell && n.status === "verified").map((n) => `${n.cell![0]}|${n.cell![1]}`));
  return (
    <div className="space-y-4">
      <Chart a={a} />
      <div className="max-h-96 overflow-auto rounded-lg border border-sand-line">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-sand-100 text-left text-xs uppercase tracking-wide text-ink-muted">
            <tr>{r.columns.map((c) => <th key={c} className="px-3 py-2 font-semibold">{c}</th>)}</tr>
          </thead>
          <tbody>{r.rows.map((row, ri) => (
            <tr key={ri} className="border-t border-sand-line">{row.map((v, ci) => {
              const hit = cited.has(`${ri}|${r.columns[ci]}`);
              return <td key={ci} className={`px-3 py-1.5 ${isNum(v) ? "text-right font-mono" : ""} ${hit ? "bg-ok-soft font-semibold text-ok" : "text-ink-body"}`}>{fmt(v)}</td>;
            })}</tr>))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-ink-muted">{r.truncated ? `Showing the first ${r.rows.length} rows. ` : ""}Highlighted cells are where the answer's numbers come from.</p>
    </div>
  );
}

const KEYWORDS = /\b(SELECT|FROM|WHERE|GROUP BY|ORDER BY|HAVING|LIMIT|JOIN|INNER JOIN|LEFT JOIN|ON|AS|AND|OR|NOT|IN|BETWEEN|WITH|CASE|WHEN|THEN|ELSE|END|DISTINCT|DESC|ASC|CAST|UNION|ALL|COUNT|SUM|AVG|MIN|MAX|YEAR|QUARTER|DATE)\b/g;
function SqlBlock({ sql }: { sql: string }) {
  const parts = sql.split(/('(?:[^']|'')*')/g);   // keep string literals out of keyword colouring
  return (
    <pre className="max-h-[28rem] overflow-auto rounded-lg bg-[#1C1917] p-4 font-mono text-[12.5px] leading-6 text-[#F5F5F4]">
      {parts.map((p, i) => p.startsWith("'") ? <span key={i} className="text-[#86EFAC]">{p}</span>
        : p.split(KEYWORDS).map((w, j) => KEYWORDS.test(w) ? (KEYWORDS.lastIndex = 0, <span key={`${i}-${j}`} className="font-semibold text-[#93C5FD]">{w}</span>) : <span key={`${i}-${j}`}>{w}</span>))}
    </pre>
  );
}

function SqlTab({ a }: { a: Answer }) {
  const r = a.result!;
  const [copied, setCopied] = useState(false);
  const download = () => {
    const blob = new Blob([JSON.stringify(a, null, 2)], { type: "application/json" });
    const link = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `nexora_answer_${a.answer_id}.json` });
    link.click(); URL.revokeObjectURL(link.href);
  };
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={() => { navigator.clipboard.writeText(a.chosen!.sql); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
          className="rounded-lg border border-sand-line bg-white px-3 py-1.5 text-sm font-medium shadow-card hover:border-ok">{copied ? "Copied ✓" : "Copy SQL"}</button>
        <button onClick={download} className="rounded-lg border border-sand-line bg-white px-3 py-1.5 text-sm font-medium shadow-card hover:border-ok">Download evidence (JSON)</button>
      </div>
      <SqlBlock sql={a.chosen!.sql} />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {[["Engine", r.engine], ["Warehouse", r.warehouse || "–"], ["Role", r.role || "–"], ["Rows", fmt(r.row_count ?? r.rows.length)], ["Snowflake time", `${r.elapsed_ms} ms`]].map(([k, v]) => (
          <Card key={k} className="px-3 py-2"><div className="text-[11px] uppercase tracking-wide text-ink-muted">{k}</div><div className="font-semibold">{v}</div></Card>))}
      </div>
      <p className="font-mono text-xs text-ink-muted">query id {r.query_id} · answer id {a.answer_id}</p>
      <div>
        <div className="mb-1 text-sm font-semibold">How it was computed</div>
        <ul className="list-disc space-y-1 pl-5 text-sm text-ink-body">{a.explanation.map((s, i) => <li key={i}>{s}</li>)}</ul>
        <p className="mt-1 text-xs text-ink-muted">Generated from the executed SQL by code, not written by the AI.</p>
      </div>
    </div>
  );
}

const LABEL: Record<string, string> = { plan: "Candidate 1 · semantic plan", sql: "Candidate 2 · Gemma SQL", sql_alt: "Candidate 3 · re-derivation" };
function ConsensusTab({ a }: { a: Answer }) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-body">{a.agreement}</p>
      <div className={`grid gap-4 ${a.candidates.length > 2 ? "lg:grid-cols-3" : "md:grid-cols-2"}`}>
        {a.candidates.map((c) => {
          const ok = !!c.result && !c.result.error, chosen = a.chosen?.name === c.name;
          return (
            <Card key={c.name} className={`p-4 ${chosen ? "ring-2 ring-ok" : ""}`}>
              <div className="mb-2 flex items-center justify-between gap-2"><span className="text-sm font-semibold">{LABEL[c.name] ?? c.name}</span>
                {chosen ? <Pill tone="ok">chosen</Pill> : <Pill tone={ok ? "neutral" : "warn"}>{ok ? "ran" : c.sql ? "failed" : "not built"}</Pill>}</div>
              {ok && <p className="text-xs text-ink-muted">{fmt(c.result!.row_count ?? c.result!.rows.length)} rows · <span className="font-mono">{c.result!.query_id}</span></p>}
              {c.issues.length > 0 && <p className="mt-1 text-xs text-bad">✗ {c.issues.join("; ")}</p>}
              {c.error && <p className="mt-1 text-xs text-warn">{c.error}</p>}
              {c.sql && <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-sand-50 p-2 font-mono text-[11px] leading-5">{c.sql}</pre>}
            </Card>);
        })}
      </div>
    </div>
  );
}

const TABS = ["📊 Data & chart", "🏛️ Verification tower", "🔍 SQL & Snowflake receipt", "⚖️ Cross-check"];
export default function Evidence({ a, health }: { a: Answer; health: Health | null }) {
  const [tab, setTab] = useState(0);
  return (
    <Card className="mt-3 p-1">
      <div className="flex flex-wrap gap-1 border-b border-sand-line px-2 pt-2" role="tablist">
        {TABS.map((t, i) => (
          <button key={t} role="tab" aria-selected={tab === i} onClick={() => setTab(i)}
            className={`-mb-px rounded-t-lg border-b-2 px-3 py-2 text-sm font-medium ${tab === i ? "border-ok text-ok" : "border-transparent text-ink-muted hover:text-ink"}`}>{t}</button>))}
      </div>
      <div className="p-4">
        {tab === 0 && <DataTab a={a} />}{tab === 1 && <Tower a={a} health={health} />}
        {tab === 2 && <SqlTab a={a} />}{tab === 3 && <ConsensusTab a={a} />}
      </div>
    </Card>
  );
}
