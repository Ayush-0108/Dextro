import type { Answer } from "../types";
import { Card, Pill, confidenceTone } from "./ui";

const STATUS: Record<string, string> = {
  answered: "Answered", empty: "No matching rows", clarify: "Needs clarification", not_in_data: "Not in this data",
  refused: "Declined", chitchat: "About Nexora", error: "Could not answer",
};
const CHIP = { verified: "bg-ok-soft text-ok ring-ok-line", derived: "bg-derive-soft text-derive ring-derive-line",
               unverified: "bg-warn-soft text-warn ring-warn-line" } as const;

/** The answer text, each number wrapped in a chip coloured by its verification status (positions from the checker). */
function Message({ a }: { a: Answer }) {
  const parts: JSX.Element[] = [];
  let pos = 0;
  [...a.number_checks].sort((x, y) => x.start - y.start).forEach((n, i) => {
    if (n.start < pos || a.message.slice(n.start, n.end).trim() !== n.text) return;
    parts.push(<span key={`t${i}`}>{a.message.slice(pos, n.start)}</span>);
    const cls = n.status in CHIP ? CHIP[n.status as keyof typeof CHIP] : "";
    parts.push(<span key={`n${i}`} title={`${n.status}${n.source ? ": " + n.source : ""}`}
      className={cls ? `mx-0.5 rounded-md px-1.5 py-0.5 font-semibold ring-1 ${cls}` : ""}>{a.message.slice(n.start, n.end)}</span>);
    pos = n.end;
  });
  parts.push(<span key="end">{a.message.slice(pos)}</span>);
  return <p className="text-[15px] leading-7 text-ink">{parts}</p>;
}

export default function Receipt({ a, onInterpret }: { a: Answer; onInterpret: (text: string) => void }) {
  const r = a.result;
  return (
    <Card className="p-5">
      <div className="mb-3 flex flex-wrap gap-2">
        <Pill tone="derive">{STATUS[a.status] ?? a.status}</Pill>
        {a.confidence && <Pill tone={confidenceTone(a.confidence)}>{a.confidence} confidence</Pill>}
        {a.chosen && r && <>
          <Pill tone="ok">✓ read-only SQL, validated</Pill>
          <Pill>⏱ {(a.timings.total_s ?? 0).toFixed(1)} s · Snowflake {r.elapsed_ms} ms</Pill>
          {r.query_id && <Pill mono>❄ {r.query_id.length > 20 ? r.query_id.slice(0, 20) + "…" : r.query_id}</Pill>}
        </>}
        {a.narration === "fallback" && a.status === "answered" && <Pill tone="warn">templated answer</Pill>}
      </div>
      <Message a={a} />
      {a.standalone_question && a.standalone_question.trim().toLowerCase() !== a.question.trim().toLowerCase() &&
        <p className="mt-2 text-xs text-ink-muted">Interpreted as: {a.standalone_question}</p>}
      {a.coverage.length > 0 && (
        <div className="mt-4 rounded-lg border border-sand-line bg-sand-50 px-3 py-2.5">
          <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">Your question → the query</div>
          <div className="flex flex-wrap gap-2">
            {a.coverage.map((c, i) => (
              <Pill key={i} tone={c.found ? "ok" : "bad"}>{c.found ? "✓" : "✗"} {c.asked}{c.where && <span className="font-normal opacity-80">· {c.where}</span>}</Pill>
            ))}
          </div>
          <p className="mt-1.5 text-[11px] text-ink-muted">Checked by code against the SQL that ran in Snowflake, not by the AI.</p>
        </div>
      )}
      {a.assumptions.length > 0 && <p className="mt-3 text-xs text-ink-muted">Assumptions: {a.assumptions.join(" · ")}</p>}
      {a.number_checks.length > 0 && (
        <p className="mt-2 text-[11px] text-ink-muted">Numbers: <b className="text-ok">green</b> found in the result rows ·
          <b className="text-derive"> blue</b> simple calculation from them · <b className="text-warn">amber</b> not verified</p>
      )}
      {a.status === "clarify" && a.interpretations.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {a.interpretations.map((t, i) => (
            <button key={i} onClick={() => onInterpret(`${a.question} (I mean: ${t})`)}
              className="rounded-lg border border-sand-line bg-white px-3 py-1.5 text-left text-sm text-ink-body shadow-card hover:border-ok hover:text-ok">{t}</button>
          ))}
        </div>
      )}
    </Card>
  );
}
