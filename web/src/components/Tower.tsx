import { useState, type ReactNode } from "react";
import type { Answer, Candidate, Health } from "../types";
import { Pill, fmt, type Tone } from "./ui";

/* ---- wires: vertical, split into two branches, merge back. One flowing dashed stroke (see .wire in index.css). */
const Line = () => (
  <svg className="mx-auto block h-7 w-4" viewBox="0 0 4 28" aria-hidden><line className="wire" x1="2" y1="0" x2="2" y2="28" /></svg>
);
const Branch = ({ merge = false }: { merge?: boolean }) => (
  <svg className="block h-8 w-full" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden>
    <path className="wire" vectorEffect="non-scaling-stroke"
      d={merge ? "M25 0 V22 H75 V0 M50 22 V32" : "M50 0 V10 M25 32 V10 H75 V32"} />
  </svg>
);

function Block({ step, icon, title, status, tone, children }: {
  step: string; icon: string; title: string; status: string; tone: Tone; children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`rounded-xl border bg-white shadow-card transition-all ${open ? "border-ink-muted/40" : "border-sand-line"}`}>
      <button onClick={() => setOpen(!open)} aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3 text-left">
        <span className="grid h-9 w-9 flex-none place-items-center rounded-lg bg-sand-100 text-lg">{icon}</span>
        <span className="min-w-0 flex-1">
          <span className="block text-[11px] font-semibold uppercase tracking-wide text-ink-muted">{step}</span>
          <span className="block truncate font-semibold text-ink">{title}</span>
        </span>
        <Pill tone={tone}>{status}</Pill>
        <span className={`text-ink-muted transition-transform ${open ? "rotate-180" : ""}`}>⌄</span>
      </button>
      <div className={`grid transition-all duration-300 ${open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"}`}>
        <div className="overflow-hidden">
          <div className="border-t border-sand-line px-4 py-3 text-sm text-ink-body">{children}</div>
        </div>
      </div>
    </div>
  );
}

const Code = ({ children }: { children: string }) => (
  <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-sand-50 p-3 font-mono text-xs leading-5 text-ink">{children}</pre>
);
const LABEL: Record<string, string> = { plan: "Semantic plan → compiled SQL", sql: "Gemma-written SQL", sql_alt: "Independent re-derivation" };
const ran = (c?: Candidate) => !!c?.result && !c.result.error;
const candStatus = (c?: Candidate) => (!c ? "not built" : ran(c) ? `ran · ${c.result!.row_count ?? c.result!.rows.length} rows` : c.sql ? "failed" : "not expressible");

export default function Tower({ a, health }: { a: Answer; health: Health | null }) {
  const plan = a.candidates.find((c) => c.name === "plan");
  const sql = a.candidates.find((c) => c.name === "sql");
  const alt = a.candidates.find((c) => c.name === "sql_alt");
  const ok = a.candidates.filter(ran);
  const repairs = a.candidates.flatMap((c) => c.attempts.filter((t) => t.stage === "validate").map((t) => ({ c, t })));
  const covered = a.coverage.filter((c) => c.found).length;
  const traced = a.number_checks.filter((n) => n.status !== "unverified").length;
  const r = a.result!;
  const sf = health?.snowflake;
  const engineTitle = r.engine === "snowflake" ? "Snowflake execution" : `Query execution (${r.engine}, offline)`;

  return (
    <div className="mx-auto max-w-3xl">
      <Block step="Layer 1" icon="🛡️" title="Read-only guard & question router" tone="ok" status="PASS · read request">
        <p>The write-intent guard found no request to change data; the router classified the question as answerable.</p>
        <p className="mt-2 text-xs text-ink-muted">Interpreted as: {a.standalone_question}</p>
        {a.assumptions.map((s, i) => <p key={i} className="mt-1 text-xs">• {s}</p>)}
      </Block>
      <Branch />
      <div className="grid grid-cols-2 gap-4">
        <Block step="Layer 2 · branch A" icon="🧠" title="Gemma semantic plan" tone={ran(plan) ? "ok" : "warn"} status={candStatus(plan)}>
          {plan?.plan ? <><p>Gemma chose <i>what</i> to compute; code compiled it using only verified joins and metrics.</p>
            <Code>{JSON.stringify(plan.plan, null, 2)}</Code></> : <p>{plan?.error ?? "No plan was built."}</p>}
          {plan?.sql && <Code>{plan.sql}</Code>}
        </Block>
        <Block step="Layer 2 · branch B" icon="✍️" title="Gemma direct SQL" tone={ran(sql) ? "ok" : "warn"} status={candStatus(sql)}>
          {sql?.sql ? <Code>{sql.sql}</Code> : <p>{sql?.error ?? "Not built."}</p>}
          {alt && <><p className="mt-3 font-medium">Independent re-derivation ({candStatus(alt)})</p>{alt.sql && <Code>{alt.sql}</Code>}</>}
        </Block>
      </div>
      <Branch merge />
      <Block step="Layer 3" icon="🔍" title="SQL validator & join rules" tone="ok"
        status={repairs.length ? `PASS after ${repairs.length} repair${repairs.length > 1 ? "s" : ""}` : "PASS · single SELECT"}>
        <p>Only one read-only SELECT over the dataset's tables: no writes, other databases, table functions, Cortex/AI calls
          or cartesian joins; known columns only; row cap. Plans join only along verified many-to-one links (no double counting).</p>
        {repairs.map(({ c, t }, i) => <p key={i} className="mt-2 text-xs">• {LABEL[c.name] ?? c.name} rejected, then repaired: {t.error}</p>)}
      </Block>
      <Line />
      <Block step="Layer 4" icon="❄️" title={engineTitle} tone="ok"
        status={`${r.warehouse ? r.warehouse + " · " : ""}${sf?.region ? sf.region + " · " : ""}${r.elapsed_ms} ms`}>
        <table className="w-full text-xs">
          <thead className="text-left text-ink-muted"><tr><th className="py-1">candidate</th><th>query id</th><th>ms</th><th>rows</th><th>role</th></tr></thead>
          <tbody className="font-mono">{ok.map((c) => (
            <tr key={c.name} className="border-t border-sand-line"><td className="py-1 font-sans">{LABEL[c.name] ?? c.name}</td>
              <td>{c.result!.query_id}</td><td>{c.result!.elapsed_ms}</td><td>{fmt(c.result!.row_count ?? c.result!.rows.length)}</td><td>{c.result!.role}</td></tr>))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-ink-muted">Each query carries a QUERY_TAG with answer id {a.answer_id}; see Snowsight → Query History.</p>
      </Block>
      <Line />
      <Block step="Layer 5" icon="🧭" title="Question → query coverage" tone={covered === a.coverage.length ? "ok" : "bad"}
        status={a.coverage.length ? `${covered} of ${a.coverage.length} conditions used` : "nothing explicit to check"}>
        {a.coverage.length ? a.coverage.map((c, i) => <p key={i}>{c.found ? "✓" : "✗"} {c.asked} <span className="text-ink-muted">{c.where}</span></p>)
          : <p>The question states no years, values, thresholds or "top N" for code to check.</p>}
        {a.candidates.filter((c) => c.issues.length).map((c) => <p key={c.name} className="mt-2 text-xs">• {LABEL[c.name] ?? c.name}: {c.issues.join("; ")}</p>)}
      </Block>
      <Line />
      <Block step="Layer 6" icon="🔢" title="Cell-level number grounding" tone={traced === a.number_checks.length && a.narration !== "fallback" ? "ok" : "warn"}
        status={a.number_checks.length ? `${traced} of ${a.number_checks.length} numbers traced to rows` : "no numbers in the answer"}>
        {a.number_checks.map((n, i) => <p key={i}><b>{n.text}</b> — {n.status}{n.source ? ` (${n.source})` : ""}</p>)}
        {a.narration === "fallback" && <p className="mt-2">Gemma's sentence used a number not in the rows, so a templated answer built only from the rows is shown.</p>}
      </Block>
      <p className="mt-3 text-center text-xs text-ink-muted">Built from this answer's own run — nothing here is a fixed claim.</p>
    </div>
  );
}
