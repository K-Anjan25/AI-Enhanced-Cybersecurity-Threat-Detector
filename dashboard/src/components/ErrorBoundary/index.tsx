import React from "react";

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error | null;
}

export class ErrorBoundary extends React.Component<React.PropsWithChildren<{}>, ErrorBoundaryState> {
  constructor(props: React.PropsWithChildren<{}>) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Send to the backend audit trail (append-only) so client errors surface
    // in the system logs instead of only the console.
    try {
      const payload = {
        message: error?.message || String(error),
        component_stack: info?.componentStack || null,
        url: typeof window !== "undefined" ? window.location.href : null,
        user_agent: typeof navigator !== "undefined" ? navigator.userAgent : null,
      };
      if (typeof navigator !== "undefined" && navigator.sendBeacon) {
        navigator.sendBeacon(
          "/api/v1/telemetry/client-error",
          new Blob([JSON.stringify(payload)], { type: "application/json" })
        );
      } else {
        void fetch("/api/v1/telemetry/client-error", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          keepalive: true,
        });
      }
    } catch (reportErr) {
      console.error("Telemetry report failed:", reportErr);
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-6 bg-app-surface text-content-primary rounded-lg">
          <h2 className="text-lg font-semibold">Something went wrong.</h2>
          <pre className="text-sm mt-2 text-content-secondary">{String(this.state.error)}</pre>
        </div>
      );
    }

    return this.props.children as React.ReactElement;
  }
}

export default ErrorBoundary;
