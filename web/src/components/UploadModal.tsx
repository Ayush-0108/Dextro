import { useState, useRef } from "react";
import type { Dataset } from "../types";
import * as api from "../api";
import { CloseIcon, DatabaseIcon, PaperclipIcon, CheckIcon } from "./icons";

const SAMPLE_CSV = `Order_ID,Customer_Name,Segment,Category,Sub_Category,Sales,Quantity,Discount,Profit,Order_Date
CA-2023-1001,John Smith,Consumer,Technology,Phones,799.99,2,0.1,120.50,2023-01-15
CA-2023-1002,Jane Doe,Corporate,Furniture,Chairs,350.00,1,0.0,45.20,2023-01-16
CA-2023-1003,Acme Corp,Home Office,Office Supplies,Binders,25.40,4,0.2,8.10,2023-01-18
CA-2023-1004,Alice Brown,Consumer,Technology,Accessories,89.50,3,0.0,22.40,2023-01-20
CA-2023-1005,Bob Wilson,Corporate,Furniture,Tables,850.00,1,0.15,110.00,2023-01-22
CA-2023-1006,Global Tech,Corporate,Technology,Machines,1200.00,1,0.05,250.00,2023-01-25
CA-2023-1007,Sarah Davis,Consumer,Office Supplies,Paper,14.50,5,0.0,5.20,2023-01-28
CA-2023-1008,Michael Scott,Corporate,Office Supplies,Paper,450.00,10,0.1,65.00,2023-02-01
CA-2023-1009,Pam Beesly,Consumer,Furniture,Furnishings,120.00,2,0.0,30.00,2023-02-03
CA-2023-1010,Jim Halpert,Corporate,Technology,Phones,1100.00,2,0.1,180.00,2023-02-05`;

export default function UploadModal({
  open,
  onClose,
  onSuccess,
}: {
  open: boolean;
  onClose: () => void;
  onSuccess: (datasets: Dataset[], newId: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [name, setName] = useState("");
  const [columnsPreview, setColumnsPreview] = useState<string[]>([]);
  const [rowCount, setRowCount] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadStep, setUploadStep] = useState("");
  const [error, setError] = useState("");
  const [successResult, setSuccessResult] = useState<{ id: string; title: string; rows: number } | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!open) return null;

  const parseCsvHeader = (text: string, filename: string) => {
    const lines = text.trim().split("\n");
    if (lines.length > 0) {
      const cols = lines[0].split(",").map((c) => c.trim().replace(/^["']|["']$/g, ""));
      setColumnsPreview(cols);
      setRowCount(Math.max(0, lines.length - 1));
    }
    const base = filename.replace(/\.[^/.]+$/, "");
    if (!name) setName(base.toLowerCase().replace(/[^a-z0-9_]/g, "_"));
    if (!title) setTitle(base.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()));
  };

  const handleFileChange = (f: File) => {
    setFile(f);
    setError("");
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = String(e.target?.result || "");
      parseCsvHeader(content, f.name);
    };
    reader.readAsText(f.slice(0, 8192));
  };

  const handleUseSample = () => {
    const sampleBlob = new Blob([SAMPLE_CSV], { type: "text/csv" });
    const sampleFile = new File([sampleBlob], "superstore_sales.csv", { type: "text/csv" });
    setFile(sampleFile);
    setTitle("Superstore Sales");
    setName("superstore_sales");
    parseCsvHeader(SAMPLE_CSV, "superstore_sales.csv");
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    setUploading(true);
    setError("");
    setUploadStep("Reading CSV and creating table...");

    try {
      const res = await api.uploadDataset(file, name, title);
      setUploadStep("Drafting verified semantic model & metrics...");
      setTimeout(() => {
        setUploading(false);
        setSuccessResult({ id: res.id, title: res.title, rows: res.rows });
        onSuccess(res.datasets, res.id);
      }, 600);
    } catch (err: unknown) {
      setUploading(false);
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleReset = () => {
    setFile(null);
    setTitle("");
    setName("");
    setColumnsPreview([]);
    setRowCount(null);
    setError("");
    setSuccessResult(null);
    setUploadStep("");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-stone-200 bg-white p-6 shadow-2xl">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-stone-100 pb-3">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200">
              <DatabaseIcon className="h-4 w-4" />
            </span>
            <div>
              <h3 className="text-base font-bold text-stone-900">Upload Dataset (CSV)</h3>
              <p className="text-[11px] text-stone-500">
                DataMind automatically creates a verified schema & metrics for your data.
              </p>
            </div>
          </div>
          <button
            onClick={() => {
              handleReset();
              onClose();
            }}
            className="rounded-lg p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-700"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </div>

        {/* Success View */}
        {successResult ? (
          <div className="mt-6 text-center space-y-4">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
              <CheckIcon className="h-6 w-6" />
            </div>
            <div>
              <h4 className="text-base font-bold text-stone-900">Dataset Loaded Successfully!</h4>
              <p className="mt-1 text-xs text-stone-600">
                Created schema and table for <b>{successResult.title}</b> ({successResult.rows} rows).
              </p>
            </div>
            <div className="flex justify-center gap-3 pt-2">
              <button
                onClick={() => {
                  handleReset();
                  onClose();
                }}
                className="rounded-xl bg-stone-900 px-5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-stone-800"
              >
                Start Asking Questions
              </button>
            </div>
          </div>
        ) : (
          /* Upload Form */
          <form onSubmit={handleUpload} className="mt-4 space-y-4">
            <input
              type="file"
              ref={fileInputRef}
              accept=".csv"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleFileChange(f);
              }}
            />

            {/* Drag & Drop Zone */}
            {!file ? (
              <div
                onClick={() => fileInputRef.current?.click()}
                className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-300 bg-stone-50/60 p-6 text-center cursor-pointer hover:border-stone-400 hover:bg-stone-100/60 transition"
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white shadow-sm text-stone-500">
                  <PaperclipIcon className="h-5 w-5" />
                </div>
                <div className="mt-3 text-xs font-semibold text-stone-800">
                  Click to browse or drag and drop a CSV file
                </div>
                <div className="mt-1 text-[11px] text-stone-400">
                  Tabular CSV files up to 50MB
                </div>

                <div className="mt-4 border-t border-stone-200/80 pt-3 w-full">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleUseSample();
                    }}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700 shadow-sm hover:bg-stone-50 hover:text-stone-900 transition"
                  >
                    ✨ Use Sample E-Commerce CSV
                  </button>
                </div>
              </div>
            ) : (
              /* Selected File Details */
              <div className="rounded-xl border border-stone-200 bg-stone-50/70 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 truncate">
                    <span className="flex h-7 w-7 items-center justify-center rounded bg-white shadow-sm text-xs font-bold text-emerald-700">
                      CSV
                    </span>
                    <span className="truncate text-xs font-semibold text-stone-900">{file.name}</span>
                    {rowCount !== null && (
                      <span className="rounded-full bg-stone-200/70 px-2 py-0.5 text-[10px] text-stone-600 font-medium">
                        ~{rowCount} rows
                      </span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={handleReset}
                    className="text-xs text-stone-400 hover:text-red-500"
                  >
                    Change
                  </button>
                </div>

                {/* Detected Columns */}
                {columnsPreview.length > 0 && (
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wider text-stone-400">
                      Detected Columns ({columnsPreview.length}):
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1 max-h-24 overflow-y-auto">
                      {columnsPreview.map((col) => (
                        <span
                          key={col}
                          className="rounded bg-white px-2 py-0.5 font-mono text-[10px] text-stone-700 border border-stone-200/80"
                        >
                          {col}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Title & Slug inputs */}
            {file && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-bold text-stone-700">Dataset Title</label>
                  <input
                    type="text"
                    required
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="e.g. Superstore Sales"
                    className="mt-1 w-full rounded-lg border border-stone-200 px-3 py-1.5 text-xs focus:border-stone-400 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-bold text-stone-700">Schema Slug</label>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. superstore_sales"
                    className="mt-1 w-full rounded-lg border border-stone-200 px-3 py-1.5 font-mono text-xs focus:border-stone-400 focus:outline-none"
                  />
                </div>
              </div>
            )}

            {/* Error Message */}
            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-2 text-xs text-red-600">
                {error}
              </div>
            )}

            {/* Uploading Status */}
            {uploading && (
              <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 p-2.5 text-xs text-emerald-800">
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
                <span>{uploadStep}</span>
              </div>
            )}

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-2 border-t border-stone-100 pt-3">
              <button
                type="button"
                onClick={() => {
                  handleReset();
                  onClose();
                }}
                disabled={uploading}
                className="rounded-lg border border-stone-200 px-3 py-1.5 text-xs font-medium text-stone-600 hover:bg-stone-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={uploading || !file}
                className="rounded-lg bg-stone-900 px-4 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-stone-800 disabled:opacity-40"
              >
                {uploading ? "Analyzing & Building..." : "Upload & Analyze Dataset"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
