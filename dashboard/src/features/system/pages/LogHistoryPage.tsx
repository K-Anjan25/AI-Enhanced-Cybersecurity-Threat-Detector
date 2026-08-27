import React, { useEffect, useRef, useState } from "react";
import { uploadLogs, fetchLogHistory, fetchUploadBatchStatus } from "../../../api/alertApi";
import type { LogHistoryEntry, UploadLogsResponse } from "../../../types/alert";
import { PageHeader, Card, SkeletonTable, EmptyState, Button } from "../../../components/ui";

const SCAN_POLL_INTERVAL_MS = 1500;
const SCAN_POLL_MAX_ATTEMPTS = 20;

const LogHistoryPage: React.FC = () => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadLogsResponse | null>(null);
  const [history, setHistory] = useState<LogHistoryEntry[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const pollTimer = useRef<number | null>(null);

  useEffect(() => {
    // Clear any pending poll timer when the page unmounts.
    return () => {
      if (pollTimer.current !== null) {
        window.clearTimeout(pollTimer.current);
      }
    };
  }, []);

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

  /**
   * The backend scans the batch asynchronously; poll /uploads/{batch_id} until
   * it completes so the real threats-detected count is shown.
   */
  const pollBatchStatus = (batchId: number, attempt = 1) => {
    pollTimer.current = window.setTimeout(async () => {
      try {
        const status = await fetchUploadBatchStatus(batchId);
        if (status.batch.status === "completed") {
          setUploadResult((prev) =>
            prev
              ? {
                  ...prev,
                  threatsDetected: status.batch.threats_detected,
                  totalLogsParsed: status.batch.total_logs,
                }
              : prev
          );
          setIsScanning(false);
          await loadHistory();
          return;
        }
        if (status.batch.status === "failed") {
          setErrorMessage(
            status.batch.message || "Background scan failed for the uploaded file."
          );
          setIsScanning(false);
          return;
        }
      } catch (error) {
        console.error(error);
      }
      if (attempt < SCAN_POLL_MAX_ATTEMPTS) {
        pollBatchStatus(batchId, attempt + 1);
      } else {
        setIsScanning(false);
      }
    }, SCAN_POLL_INTERVAL_MS);
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
      setIsLoading(false);
      // Scan runs in the background; follow it until the batch completes.
      setIsScanning(true);
      pollBatchStatus(result.batch_id);
    } catch (err) {
      console.error(err);
      setErrorMessage("Upload failed. Please check the file and try again.");
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Log Upload & History"
        description="Upload log files for automated threat scanning and review previous upload results."
      />

      <Card>
        <div className="grid gap-4 sm:grid-cols-[1fr_auto] items-end">
          <label className="block">
            <span className="text-sm font-medium text-content-secondary">Choose a log file</span>
            <input
              type="file"
              accept=".json,.csv,.log,.txt"
              onChange={handleFileChange}
              className="mt-2 block w-full text-sm text-content-primary file:border file:px-4 file:py-2 file:rounded-lg file:border-line-subtle file:bg-app-subtle file:text-content-primary file:cursor-pointer file:hover:bg-line-bright file:transition"
            />
          </label>

          <Button
            type="button"
            onClick={handleUpload}
            disabled={!selectedFile || isLoading}
          >
            {isLoading ? "Uploading…" : "Upload and Scan"}
          </Button>
        </div>

        {errorMessage && (
          <div className="mt-4 rounded-xl bg-status-critical/10 border border-status-critical/30 p-4 text-sm text-status-critical">
            {errorMessage}
          </div>
        )}

        {uploadResult && (
          <div className="mt-4 rounded-xl bg-status-success/10 border border-status-success/30 p-4 text-sm text-status-success">
            <p className="font-medium">{uploadResult.message}</p>
            <p>File: {uploadResult.filename}</p>
            <p>Scanned: {uploadResult.totalLogsParsed ?? 0}</p>
            <p>
              Threats Detected:{" "}
              {isScanning ? "scanning…" : (uploadResult.threatsDetected ?? 0)}
            </p>
          </div>
        )}
      </Card>

      <Card padded={false} className="overflow-hidden">
        <div className="flex items-center justify-between gap-3 px-6 pt-5">
          <div>
            <h2 className="text-lg font-semibold text-content-primary">Upload History</h2>
            <p className="text-xs text-content-tertiary mt-0.5">Previous uploads and their scan results.</p>
          </div>
          <Button
            type="button"
            variant="secondary"
            onClick={loadHistory}
            disabled={isLoading}
          >
            Refresh
          </Button>
        </div>

        {isLoading ? (
          <SkeletonTable rows={5} cols={4} />
        ) : history.length === 0 ? (
          <EmptyState
            title="No log uploads recorded yet"
            description="Upload a log file above to begin automated scanning."
          />
        ) : (
          <div className="overflow-x-auto mt-4">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-app-subtle border-b border-line-subtle text-xs font-semibold uppercase tracking-wider text-content-secondary">
                  <th scope="col" className="px-4 py-3">File</th>
                  <th scope="col" className="px-4 py-3">Parsed</th>
                  <th scope="col" className="px-4 py-3">Threats</th>
                  <th scope="col" className="px-4 py-3">Uploaded</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-subtle text-sm">
                {history.map((entry) => (
                  <tr key={`${entry.filename}-${entry.timestamp}`} className="hover:bg-app-subtle/50 transition-colors">
                    <td className="px-4 py-3 font-medium text-content-primary">{entry.filename}</td>
                    <td className="px-4 py-3">{entry.totalLogsParsed}</td>
                    <td className="px-4 py-3">{entry.threatsDetected}</td>
                    <td className="px-4 py-3 text-content-secondary">
                      {entry.timestamp ? new Date(entry.timestamp).toLocaleString() : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};

export default LogHistoryPage;
