import { useState } from "react";
import type { Health } from "../types";
import {
  DataMindLogo,
  CollapseSidebarIcon,
  SparkleIcon,
  DatabaseIcon,
  ChatBubbleIcon,
  SearchIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  BookmarkIcon,
  UserAvatarIcon,
  MoonIcon,
  SettingsIcon,
  PaperclipIcon,
} from "./icons";

export default function Sidebar({
  currentView,
  onSelectView,
  health,
  onNew,
  history,
  onSelectHistory,
  onClearHistory,
  onOpenSettings,
  onOpenUpload,
}: {
  currentView: "ask" | "explorer" | "saved";
  onSelectView: (v: "ask" | "explorer" | "saved") => void;
  health: Health | null;
  onNew: () => void;
  history: string[];
  onSelectHistory: (q: string) => void;
  onClearHistory: () => void;
  onOpenSettings: () => void;
  onOpenUpload: () => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(true);
  const [historyFilter, setHistoryFilter] = useState("");

  const filteredHistory = history.filter((q) =>
    q.toLowerCase().includes(historyFilter.toLowerCase())
  );

  const isHealthy = health?.snowflake?.state === "ok";

  if (collapsed) {
    return (
      <aside className="flex h-full w-14 flex-none flex-col items-center justify-between border-r border-stone-200/80 bg-white py-4 shadow-sm">
        <div className="flex flex-col items-center gap-4">
          <button
            onClick={() => setCollapsed(false)}
            title="Expand sidebar"
            className="rounded-lg p-1 text-stone-600 hover:bg-stone-100"
          >
            <DataMindLogo className="h-6 w-6" />
          </button>
          <button
            onClick={() => {
              onSelectView("ask");
              onNew();
            }}
            title="New Chat"
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-stone-200 text-stone-700 hover:bg-stone-100"
          >
            +
          </button>
          <button
            onClick={() => onSelectView("ask")}
            title="Ask Data"
            className={`flex h-9 w-9 items-center justify-center rounded-lg ${
              currentView === "ask" ? "bg-blue-50 text-blue-600" : "text-stone-600 hover:bg-stone-100"
            }`}
          >
            <SparkleIcon className="h-4 w-4" />
          </button>
          <button
            onClick={() => onSelectView("explorer")}
            title="Data Explorer"
            className={`flex h-9 w-9 items-center justify-center rounded-lg ${
              currentView === "explorer" ? "bg-blue-50 text-blue-600" : "text-stone-600 hover:bg-stone-100"
            }`}
          >
            <DatabaseIcon className="h-4 w-4" />
          </button>
          <button
            onClick={() => onSelectView("saved")}
            title="Saved Analyses"
            className={`flex h-9 w-9 items-center justify-center rounded-lg ${
              currentView === "saved" ? "bg-blue-50 text-blue-600" : "text-stone-600 hover:bg-stone-100"
            }`}
          >
            <BookmarkIcon className="h-4 w-4" />
          </button>
          <button
            onClick={onOpenUpload}
            title="Upload Dataset (CSV)"
            className="flex h-9 w-9 items-center justify-center rounded-lg text-emerald-600 hover:bg-emerald-50 transition"
          >
            <PaperclipIcon className="h-4 w-4" />
          </button>
        </div>
        <button
          onClick={onOpenSettings}
          title="Settings"
          className="rounded-lg p-2 text-stone-500 hover:bg-stone-100 relative"
        >
          <SettingsIcon className="h-4 w-4" />
          <span
            className={`absolute top-1.5 right-1.5 h-1.5 w-1.5 rounded-full ${
              isHealthy ? "bg-emerald-500" : "bg-amber-500"
            }`}
          />
        </button>
      </aside>
    );
  }

  return (
    <aside className="flex h-full w-[260px] flex-none flex-col justify-between border-r border-stone-200/80 bg-white select-none">
      {/* Top Section */}
      <div className="flex flex-col gap-3 px-3.5 pt-4">
        {/* Brand & Collapse */}
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-2">
            <DataMindLogo />
            <span className="text-[15px] font-bold tracking-tight text-stone-900">DataMind</span>
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                isHealthy ? "bg-emerald-500" : "bg-amber-500"
              }`}
              title={isHealthy ? "Snowflake & Gemma Live" : "Checking status..."}
            />
          </div>
          <button
            onClick={() => setCollapsed(true)}
            title="Collapse sidebar"
            className="rounded-lg p-1.5 text-stone-400 hover:bg-stone-100 hover:text-stone-700 transition"
          >
            <CollapseSidebarIcon />
          </button>
        </div>

        {/* New Chat Button */}
        <button
          onClick={() => {
            onSelectView("ask");
            onNew();
          }}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-stone-200/90 bg-[#FBFBFA] px-3 py-2 text-xs font-semibold text-stone-800 shadow-[0_1px_2px_rgba(0,0,0,0.03)] hover:bg-stone-100/80 hover:border-stone-300 transition"
        >
          <span>+</span>
          <span>New Chat</span>
        </button>

        {/* Navigation Items */}
        <div className="flex flex-col gap-0.5 pt-1">
          {/* Ask Data */}
          <button
            onClick={() => onSelectView("ask")}
            className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-xs font-medium transition ${
              currentView === "ask"
                ? "bg-blue-50/80 text-blue-600 font-semibold"
                : "text-stone-700 hover:bg-stone-100/70"
            }`}
          >
            <SparkleIcon className={`h-4 w-4 ${currentView === "ask" ? "text-blue-600" : "text-stone-500"}`} />
            <span>Ask Data</span>
          </button>

          {/* Data Explorer */}
          <button
            onClick={() => onSelectView("explorer")}
            className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-xs font-medium transition ${
              currentView === "explorer"
                ? "bg-blue-50/80 text-blue-600 font-semibold"
                : "text-stone-700 hover:bg-stone-100/70"
            }`}
          >
            <DatabaseIcon className={`h-4 w-4 ${currentView === "explorer" ? "text-blue-600" : "text-stone-500"}`} />
            <span>Data Explorer</span>
          </button>

          {/* Upload CSV */}
          <button
            onClick={onOpenUpload}
            className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-xs font-medium text-stone-700 hover:bg-stone-100/70 transition"
          >
            <div className="flex items-center gap-2.5">
              <PaperclipIcon className="h-4 w-4 text-emerald-600" />
              <span>Upload Dataset</span>
            </div>
            <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 border border-emerald-200">
              CSV
            </span>
          </button>
        </div>

        {/* History Section */}
        <div className="flex flex-col pt-2">
          {/* Collapsible History Header */}
          <div className="flex w-full items-center justify-between px-1 py-1 text-xs text-stone-600">
            <button
              onClick={() => setHistoryOpen(!historyOpen)}
              className="flex items-center gap-2 hover:text-stone-900 transition"
            >
              <ChatBubbleIcon className="h-3.5 w-3.5 text-stone-500" />
              <span className="font-medium text-stone-700">History</span>
              {history.length > 0 && (
                <span className="rounded-full bg-stone-100 px-1.5 py-0.2 text-[10px] font-semibold text-stone-500">
                  {history.length}
                </span>
              )}
            </button>
            <div className="flex items-center gap-2">
              {history.length > 0 && (
                <button
                  onClick={onClearHistory}
                  title="Clear history"
                  className="text-[10px] text-stone-400 hover:text-red-500"
                >
                  Clear
                </button>
              )}
              <button
                onClick={() => setHistoryOpen(!historyOpen)}
                className="text-stone-400 hover:text-stone-700"
              >
                {historyOpen ? (
                  <ChevronDownIcon className="h-3.5 w-3.5" />
                ) : (
                  <ChevronRightIcon className="h-3.5 w-3.5" />
                )}
              </button>
            </div>
          </div>

          {/* History Search & List */}
          {historyOpen && (
            <div className="mt-1.5 flex flex-col gap-1.5">
              {/* Filter history search input */}
              <div className="relative flex items-center">
                <SearchIcon className="absolute left-2.5 h-3.5 w-3.5 text-stone-400 pointer-events-none" />
                <input
                  type="text"
                  value={historyFilter}
                  onChange={(e) => setHistoryFilter(e.target.value)}
                  placeholder="Filter history..."
                  className="w-full rounded-lg border border-stone-200/80 bg-stone-50/60 py-1.5 pl-8 pr-2.5 text-[11px] text-stone-800 placeholder:text-stone-400 focus:bg-white focus:border-stone-300 focus:outline-none transition"
                />
              </div>

              {/* Past Queries List */}
              <div className="max-h-48 overflow-y-auto space-y-0.5 pr-0.5 pt-0.5">
                {filteredHistory.length > 0 ? (
                  filteredHistory.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => {
                        onSelectView("ask");
                        onSelectHistory(q);
                      }}
                      title={q}
                      className="group flex w-full items-center rounded-lg px-2 py-1.5 text-left text-[11px] text-stone-600 hover:bg-stone-100/80 hover:text-stone-900 transition"
                    >
                      <span className="truncate">{q}</span>
                    </button>
                  ))
                ) : (
                  <div className="px-2 py-2 text-[11px] text-stone-400 text-center">
                    {history.length === 0 ? "No queries yet" : "No matches"}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Saved Analyses */}
        <div className="pt-1">
          <button
            onClick={() => onSelectView("saved")}
            className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-xs font-medium transition ${
              currentView === "saved"
                ? "bg-blue-50/80 text-blue-600 font-semibold"
                : "text-stone-700 hover:bg-stone-100/70"
            }`}
          >
            <BookmarkIcon className={`h-4 w-4 ${currentView === "saved" ? "text-blue-600" : "text-stone-500"}`} />
            <span>Saved Analyses</span>
          </button>
        </div>
      </div>

      {/* Bottom Profile Bar */}
      <div className="border-t border-stone-200/80 p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 overflow-hidden">
            <div className="flex h-7 w-7 flex-none items-center justify-center rounded-full bg-stone-100 text-stone-600">
              <UserAvatarIcon className="h-4 w-4" />
            </div>
            <div className="truncate text-left leading-tight">
              <div className="truncate text-xs font-semibold text-stone-900">Local Demo ...</div>
              <div className="truncate text-[10px] text-stone-400">Local Workspa...</div>
            </div>
          </div>
          <div className="flex items-center gap-0.5 flex-none">
            <button
              onClick={() => {
                document.documentElement.classList.toggle("dark");
              }}
              title="Toggle theme"
              className="rounded-lg p-1.5 text-stone-400 hover:bg-stone-100 hover:text-stone-700 transition"
            >
              <MoonIcon className="h-4 w-4" />
            </button>
            <button
              onClick={onOpenSettings}
              title="Settings & System Health"
              className="rounded-lg p-1.5 text-stone-400 hover:bg-stone-100 hover:text-stone-700 transition relative"
            >
              <SettingsIcon className="h-4 w-4" />
              <span
                className={`absolute top-1 right-1 h-1.5 w-1.5 rounded-full ${
                  isHealthy ? "bg-emerald-500" : "bg-amber-500"
                }`}
              />
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
}
