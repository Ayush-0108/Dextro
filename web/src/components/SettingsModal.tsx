import type { Health } from "../types";
import { CloseIcon, SettingsIcon, CheckIcon } from "./icons";

export default function SettingsModal({
  open,
  onClose,
  health,
  role,
  onRole,
}: {
  open: boolean;
  onClose: () => void;
  health: Health | null;
  role: "analyst" | "restricted";
  onRole: (r: "analyst" | "restricted") => void;
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-stone-200 bg-white p-6 shadow-2xl">
        <div className="flex items-center justify-between border-b border-stone-100 pb-4">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-stone-100 text-stone-700">
              <SettingsIcon className="h-4 w-4" />
            </span>
            <h3 className="text-base font-bold text-stone-900">Settings & System Health</h3>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-700"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-4 space-y-4 max-h-[70vh] overflow-y-auto pr-1">
          {/* Active Execution Role */}
          <div className="rounded-xl border border-stone-200 bg-stone-50/50 p-4">
            <label className="text-xs font-bold uppercase tracking-wider text-stone-500">
              Snowflake Execution Role
            </label>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <button
                onClick={() => onRole("analyst")}
                className={`rounded-lg border p-3 text-left transition ${
                  role === "analyst"
                    ? "border-stone-900 bg-stone-900 text-white font-medium shadow-sm"
                    : "border-stone-200 bg-white text-stone-700 hover:border-stone-300"
                }`}
              >
                <div className="text-xs font-bold">DATAMIND_AGENT</div>
                <div className={`mt-0.5 text-[11px] ${role === "analyst" ? "text-stone-300" : "text-stone-500"}`}>
                  Standard read-only analyst (SELECT only)
                </div>
              </button>
              <button
                onClick={() => onRole("restricted")}
                className={`rounded-lg border p-3 text-left transition ${
                  role === "restricted"
                    ? "border-stone-900 bg-stone-900 text-white font-medium shadow-sm"
                    : "border-stone-200 bg-white text-stone-700 hover:border-stone-300"
                }`}
              >
                <div className="text-xs font-bold">DATAMIND_RESTRICTED</div>
                <div className={`mt-0.5 text-[11px] ${role === "restricted" ? "text-stone-300" : "text-stone-500"}`}>
                  PII-masked (phones, emails, balances redacted)
                </div>
              </button>
            </div>
          </div>

          {/* Infrastructure Health */}
          <div className="rounded-xl border border-stone-200 bg-white p-4 space-y-3">
            <div className="text-xs font-bold uppercase tracking-wider text-stone-500">
              Connected Infrastructure
            </div>

            {/* Snowflake */}
            <div className="flex items-start justify-between border-b border-stone-100 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${health?.snowflake?.state === "ok" ? "bg-emerald-500" : health?.snowflake?.state === "warn" ? "bg-amber-500" : "bg-red-500"}`} />
                  <span className="text-xs font-bold text-stone-900">Snowflake Enterprise</span>
                  <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 border border-emerald-200">
                    {health?.snowflake?.label || "Live"}
                  </span>
                </div>
                <div className="mt-1 text-xs text-stone-500">
                  {health?.snowflake?.region ? `AWS ${health.snowflake.region}` : "AWS Mumbai (AP-SOUTH-1)"} • FCBWKQT-GK18385
                </div>
                <div className="mt-0.5 text-[11px] text-stone-400 font-mono">
                  Warehouse: {health?.snowflake?.warehouse || "DATAMIND_WH"} • Version: {health?.snowflake?.version || "Live"}
                </div>
              </div>
            </div>

            {/* Ollama Gemma */}
            <div className="flex items-start justify-between border-b border-stone-100 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${health?.gemma?.state === "ok" ? "bg-emerald-500" : "bg-red-500"}`} />
                  <span className="text-xs font-bold text-stone-900">Google Gemma 4</span>
                  <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-semibold text-blue-700 border border-blue-200">
                    {health?.gemma?.label || "Local Ollama"}
                  </span>
                </div>
                <div className="mt-1 text-xs text-stone-500">
                  {health?.gemma?.detail || "gemma4:12b @ http://localhost:11434"}
                </div>
                <div className="mt-0.5 text-[11px] text-emerald-600 font-medium">
                  ✓ Gate G2 compliant: Zero cloud/paid API dependency
                </div>
              </div>
            </div>

            {/* Dual Verification */}
            <div>
              <div className="flex items-center gap-2">
                <CheckIcon className="h-4 w-4 text-emerald-600" />
                <span className="text-xs font-bold text-stone-900">Verification Tower</span>
              </div>
              <div className="mt-1 text-xs text-stone-500">
                5-Layer Deterministic Pipeline: Dual-Candidate Planning, AST Validation, Consensus Engine, Cell-Level Fact Checking.
              </div>
            </div>
          </div>

          {/* GitHub CI status */}
          <div className="flex items-center justify-between rounded-xl border border-stone-200 bg-stone-50/50 px-4 py-3">
            <span className="text-xs text-stone-600">Automated GitHub Actions CI:</span>
            <a
              href="https://github.com/ZERODAY-2026/Dextro/actions/workflows/tests.yml"
              target="_blank"
              rel="noreferrer"
            >
              <img
                alt="tests (live CI status)"
                src="https://github.com/ZERODAY-2026/Dextro/actions/workflows/tests.yml/badge.svg"
                className="h-5"
              />
            </a>
          </div>
        </div>

        <div className="mt-6 flex justify-end">
          <button
            onClick={onClose}
            className="rounded-lg bg-stone-900 px-4 py-2 text-xs font-semibold text-white hover:bg-stone-800"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
