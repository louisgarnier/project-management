"use client";

import { useState } from "react";

type Props = {
  onClose: () => void;
  onCreate: (title: string) => Promise<void>;
};

export default function NewCallModal({ onClose, onCreate }: Props) {
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await onCreate(title.trim());
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create call");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-lg w-full max-w-md p-6">
        <h2 className="text-[16px] font-semibold text-[#172b4d] mb-4">New Call</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-[12px] font-semibold text-[#5e6c84] mb-1">
              Call title
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
              className="w-full border-2 border-[#dfe1e6] focus:border-[#4c9aff] rounded px-[10px] py-2 text-[14px] text-[#172b4d] outline-none"
              placeholder="e.g. Q2 Earnings Review"
              required
            />
            <p className="text-[11px] text-[#5e6c84] mt-1.5">
              The call will start in the &ldquo;Get Transcript&rdquo; stage.
            </p>
          </div>
          {error && <p className="text-red-600 text-sm">{error}</p>}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-[6px] text-[13px] font-medium text-[#5e6c84] border border-[#dfe1e6] rounded hover:bg-[#f4f5f7]"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !title.trim()}
              className="bg-[#0052cc] text-white px-4 py-[6px] rounded text-[13px] font-medium hover:bg-[#0065ff] disabled:opacity-50"
            >
              {loading ? "Creating…" : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
