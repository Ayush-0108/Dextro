import { BookmarkIcon, SparkleIcon } from "./icons";

export interface SavedItem {
  id: string;
  question: string;
  datasetTitle: string;
  timestamp: number;
}

export default function SavedAnalyses({
  saved,
  onRun,
  onRemove,
}: {
  saved: SavedItem[];
  onRun: (q: string) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <div className="flex h-full flex-col overflow-y-auto bg-[#FAFAF9] p-8">
      <div className="mx-auto w-full max-w-4xl space-y-6">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-stone-100 text-stone-700">
              <BookmarkIcon className="h-4 w-4" />
            </span>
            <h2 className="text-xl font-bold tracking-tight text-stone-900">Saved Analyses</h2>
          </div>
          <p className="mt-1 text-sm text-stone-500">
            Pin and review your most valuable queries, verified answers, and audit receipts.
          </p>
        </div>

        {saved.length === 0 ? (
          <div className="rounded-2xl border border-stone-200/80 bg-white p-12 text-center shadow-sm">
            <BookmarkIcon className="mx-auto h-8 w-8 text-stone-300" />
            <h3 className="mt-3 text-sm font-semibold text-stone-700">No saved analyses yet</h3>
            <p className="mt-1 text-xs text-stone-400">
              When querying your data, bookmark any result to save it here for fast presentation to judges.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {saved.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between rounded-xl border border-stone-200 bg-white p-4 shadow-sm transition hover:shadow"
              >
                <div>
                  <div className="font-medium text-stone-900">{item.question}</div>
                  <div className="mt-1 flex items-center gap-2 text-xs text-stone-400">
                    <span className="rounded bg-stone-100 px-2 py-0.5 text-stone-600 font-medium">
                      {item.datasetTitle}
                    </span>
                    <span>•</span>
                    <span>{new Date(item.timestamp).toLocaleDateString()}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => onRun(item.question)}
                    className="flex items-center gap-1.5 rounded-lg bg-stone-900 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-stone-800"
                  >
                    <SparkleIcon className="h-3 w-3" />
                    Re-run
                  </button>
                  <button
                    onClick={() => onRemove(item.id)}
                    className="rounded-lg border border-stone-200 px-2.5 py-1.5 text-xs text-stone-400 hover:text-red-600"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
