import type { ReactNode } from "react";

export type Tone = "ok" | "derive" | "warn" | "bad" | "neutral";
const TONES: Record<Tone, string> = {
  ok: "bg-ok-soft text-ok border-ok-line", derive: "bg-derive-soft text-derive border-derive-line",
  warn: "bg-warn-soft text-warn border-warn-line", bad: "bg-bad-soft text-bad border-bad-line",
  neutral: "bg-white text-ink-body border-sand-line",
};

export function Pill({ tone = "neutral", children, mono = false }: { tone?: Tone; children: ReactNode; mono?: boolean }) {
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${TONES[tone]} ${mono ? "font-mono font-medium" : ""}`}>{children}</span>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-sand-line bg-white shadow-card ${className}`}>{children}</div>;
}

export const confidenceTone = (c: string | null): Tone => (c === "high" ? "ok" : c === "medium" ? "warn" : c === "low" ? "bad" : "neutral");

export function fmt(v: unknown): string {
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  return v === null || v === undefined ? "∅" : String(v);
}
