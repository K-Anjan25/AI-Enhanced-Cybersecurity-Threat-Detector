// ---------------------------------------------------------------------------
// TYPES & INTERFACES
// ---------------------------------------------------------------------------

export type ThreatSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface AlertExportItem {
  id?: string | number;
  _id?: string | number;
  created_at?: string;
  timestamp?: string;
  severity?: ThreatSeverity | string;
  risk?: ThreatSeverity | string;
  message?: string;
  title?: string;
  remediation?: string;
  details?: string;
  raw?: string;
}

// ---------------------------------------------------------------------------
// CSV EXPORT UTILITY
// ---------------------------------------------------------------------------

/**
 * Converts security alerts into a downloadable CSV report file.
 *
 * @param alerts - Array of scanned or saved security alert objects.
 * @param filename - Optional custom filename for the downloaded CSV.
 */
export const exportAlertsToCSV = (
  alerts: AlertExportItem[],
  filename: string = "scanned_security_alerts_report.csv"
): void => {
  if (!alerts || alerts.length === 0) {
    alert("No scanned or saved alerts available to export.");
    return;
  }

  // 1. Define CSV headers
  const headers: string[] = [
    "ID",
    "Timestamp",
    "Severity / Risk",
    "Message",
    "Remediation / Details",
  ];

  // 2. Map fields from both scanned_alerts and security_alerts
  const rows: string[][] = alerts.map((alertItem: AlertExportItem) => {
    const id = alertItem.id ?? alertItem._id ?? "N/A";
    const timestamp =
      alertItem.created_at || alertItem.timestamp || new Date().toLocaleString();
    const severity = alertItem.severity || alertItem.risk || "MEDIUM";

    const rawMessage = alertItem.message || alertItem.title || "";
    const escapedMessage = `"${rawMessage.replace(/"/g, '""')}"`;

    const rawDetails =
      alertItem.remediation || alertItem.details || alertItem.raw || "";
    const escapedDetails = `"${rawDetails.replace(/"/g, '""')}"`;

    return [String(id), timestamp, String(severity), escapedMessage, escapedDetails];
  });

  // 3. Create CSV content string
  const csvContent: string = [
    headers.join(","),
    ...rows.map((row: string[]) => row.join(",")),
  ].join("\n");

  // 4. Trigger browser file download
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url: string = URL.createObjectURL(blob);
  const link: HTMLAnchorElement = document.createElement("a");

  link.setAttribute("href", url);
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};