import React, { useEffect, useState } from "react";
import { uploadLogs, fetchLogHistory } from "../api/alertApi";
import type { LogHistoryEntry, UploadLogsResponse } from "../types/alert";

const LogHistoryPage: React.FC = () => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadLogsResponse | null>(null);
  const [history, setHistory] = useState<LogHistoryEntry[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadHistory = async () => {
    try {
      setIsLoading(true);
      const logs = await fetchLogHistory();
      setHistory(logs);
    } catch (error) {
      console.error(error);
      setErrorMessage("Unable to load log history.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    setUploadResult(null);
    setErrorMessage(null);
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setErrorMessage("Please choose a file before uploading.");
      return;
    }

    try {
      setIsLoading(true);
      setErrorMessage(null);
      const result = await uploadLogs(selectedFile);
      setUploadResult(result);
      await loadHistory();
    } catch (err) {
      console.error(err);
      setErrorMessage("Upload failed. Please check the file and try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-content-primary">Log Upload & History</h1>
          <p className="text-sm text-content-secondary mt-1">
            Upload log files for automated threat scanning and review previous upload results.
          </p>
        </div>
      </div>

      <section className="bg-app-surface border border-line-subtle rounded-2xl p-6 shadow-sm">
        <div className="grid gap-4 sm:grid-cols-[1fr_auto] items-end">
          <label className="block">
            <span className="text-sm font-medium text-content-secondary">Choose a log file</span>
            <input
              type="file"
              accept=".json,.csv,.log,.txt"
              onChange={handleFileChange}
              className="mt-2 block w-full text-sm text-content-primary file:border file:px-4 file:py-2 file:rounded-lg file:border-line-subtle file:bg-app-subtle file:text-content-primary"
            />
          </label>

          <button
            type="button"
            onClick={handleUpload}
            disabled={!selectedFile || isLoading}
            className="rounded-xl bg-accent-primary px-5 py-3 text-sm font-semibold text-app-bg transition hover:bg-accent-secondary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? "Uploading..." : "Upload and Scan"}
          </button>
        </div>

        {errorMessage && (
          <div className="mt-4 rounded-xl bg-red-500/10 border border-red-500/30 p-4 text-sm text-red-400">
            {errorMessage}
          </div>
        )}

        {uploadResult && (
          <div className="mt-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 p-4 text-sm text-status-success">
            <p className="font-medium">{uploadResult.message}</p>
            <p>File: {uploadResult.filename}</p>
            <p>Scanned: {uploadResult.totalLogsParsed ?? 0}</p>
            <p>Threats Detected: {uploadResult.threatsDetected ?? 0}</p>
          </div>
        )}
      </section>

      <section className="bg-app-surface border border-line-subtle rounded-2xl p-6 shadow-sm">
        <div className="flex items-center justify-between gap-3 mb-4">
          <h2 className="text-lg font-semibold text-content-primary">Upload History</h2>
          <button
            type="button"
            onClick={loadHistory}
            disabled={isLoading}
            className="rounded-xl bg-app-subtle px-4 py-2 text-sm text-content-secondary hover:bg-line-bright transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Refresh
          </button>
        </div>

        {isLoading && <p className="text-sm text-content-secondary">Loading history…</p>}

        {!isLoading && history.length === 0 && (
          <p className="text-sm text-content-secondary">No log uploads recorded yet.</p>
        )}

        {history.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-app-subtle border-b border-line-subtle text-xs font-semibold uppercase tracking-wider text-content-secondary">
                  <th className="px-4 py-3">File</th>
                  <th className="px-4 py-3">Parsed</th>
                  <th className="px-4 py-3">Threats</th>
                  <th className="px-4 py-3">Uploaded</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-subtle text-sm">
                {history.map((entry) => (
                  <tr key={`${entry.filename}-${entry.timestamp}`}>
                    <td className="px-4 py-3 font-medium text-content-primary">{entry.filename}</td>
                    <td className="px-4 py-3">{entry.totalLogsParsed}</td>
                    <td className="px-4 py-3">{entry.threatsDetected}</td>
                    <td className="px-4 py-3 text-content-secondary">{new Date(entry.timestamp).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
};

export default LogHistoryPage;
