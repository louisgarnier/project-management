"use client";

import { useEffect, useRef, useState } from "react";
import { filesAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call, CallFile } from "@/types";

const ACCEPTED = ".txt,.pdf,.docx,.csv,.md";
const MAX_MB = 10;

interface Props {
  call: Call;
  readonly?: boolean;
}

export default function ContextFiles({ call, readonly = false }: Props) {
  const [files, setFiles] = useState<CallFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    filesAPI
      .list(call.id)
      .then(setFiles)
      .catch((err) => {
        logger.error("Failed to load files", { component: "ContextFiles", data: err });
      });
  }, [call.id]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`File exceeds ${MAX_MB}MB limit`);
      return;
    }

    setUploading(true);
    setError(null);
    try {
      const uploaded = await filesAPI.upload(call.id, file);
      setFiles((prev) => [...prev, uploaded]);
      logger.info("File uploaded", { component: "ContextFiles", data: { name: file.name } });
    } catch (err) {
      logger.error("Upload failed", { component: "ContextFiles", data: err });
      setError(err instanceof Error ? err.message : "Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(fileId: string, filename: string) {
    if (!confirm(`Delete "${filename}"?`)) return;
    setError(null);
    try {
      await filesAPI.delete(call.id, fileId);
      setFiles((prev) => prev.filter((f) => f.id !== fileId));
      logger.info("File deleted", { component: "ContextFiles", data: { fileId } });
    } catch (err) {
      logger.error("Delete failed", { component: "ContextFiles", data: err });
      setError(err instanceof Error ? err.message : "Delete failed. Please try again.");
    }
  }

  async function handleDownload(fileId: string, filename: string) {
    setError(null);
    try {
      const { url } = await filesAPI.downloadUrl(call.id, fileId);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      logger.info("File download started", { component: "ContextFiles", data: { filename } });
    } catch (err) {
      logger.error("Download failed", { component: "ContextFiles", data: err });
      setError(err instanceof Error ? err.message : "Download failed. Please try again.");
    }
  }

  function formatSize(bytes: number | null): string {
    if (!bytes) return "—";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  return (
    <div className="mt-4 border border-[#dfe1e6] rounded-lg bg-white">
      <div className="px-4 py-3 border-b border-[#dfe1e6] flex items-center justify-between">
        <span className="text-[13px] font-semibold text-[#172b4d]">
          Context Files
          {files.length > 0 && (
            <span className="ml-1.5 text-[11px] font-normal text-[#5e6c84]">
              ({files.length})
            </span>
          )}
        </span>
        {!readonly && (
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="text-[11px] font-medium text-white bg-[#0052cc] px-3 py-1 rounded hover:bg-[#0747a6] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {uploading ? "Uploading…" : "+ Add file"}
          </button>
        )}
      </div>

      {error && (
        <div className="mx-4 mt-2 text-[12px] text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
          {error}
        </div>
      )}

      {files.length === 0 ? (
        <p className="px-4 py-3 text-[12px] text-[#97a0af]">
          {readonly
            ? "No context files attached."
            : "No files yet. Add reference documents to help with artifact drafting."}
        </p>
      ) : (
        <ul className="divide-y divide-[#dfe1e6]">
          {files.map((f) => (
            <li key={f.id} className="px-4 py-2.5 flex items-center gap-3">
              <span className="text-[12px] text-[#172b4d] flex-1 truncate">{f.filename}</span>
              <span className="text-[11px] text-[#97a0af] flex-shrink-0">
                {formatSize(f.size_bytes)}
              </span>
              <button
                onClick={() => handleDownload(f.id, f.filename)}
                className="text-[11px] text-[#0052cc] hover:underline flex-shrink-0"
                title="Download"
              >
                ↓
              </button>
              {!readonly && (
                <button
                  onClick={() => handleDelete(f.id, f.filename)}
                  className="text-[11px] text-[#97a0af] hover:text-red-500 flex-shrink-0"
                  title="Delete"
                >
                  ✕
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {!readonly && (
        <input
          ref={fileRef}
          type="file"
          accept={ACCEPTED}
          className="hidden"
          onChange={handleUpload}
        />
      )}
    </div>
  );
}
