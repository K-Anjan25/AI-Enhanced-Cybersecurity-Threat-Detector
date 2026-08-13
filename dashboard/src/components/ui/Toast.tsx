import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

export type ToastTone = "success" | "error" | "info" | "warning";

export interface Toast {
  id: number;
  message: string;
  tone: ToastTone;
}

interface ToastContextValue {
  push: (message: string, tone?: ToastTone) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const AUTO_DISMISS_MS = 4000;

// Bridge so non-React call sites (utils) can push toasts. The provider
// registers itself on mount; until then, calls degrade to console.
let bridgePush: (message: string, tone?: ToastTone) => void = (m, t) => {
  console.log(`[SOC ${t ?? "toast"}]: ${m}`);
};

export function getToastPusher(): (message: string, tone?: ToastTone) => void {
  return bridgePush;
}

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (message: string, tone: ToastTone = "success") => {
      const id = nextId.current++;
      setToasts((prev) => [...prev.slice(-3), { id, message, tone }]);
      window.setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    },
    [dismiss]
  );

  useEffect(() => {
    bridgePush = push;
    return () => {
      bridgePush = getToastPusher();
    };
  }, [push]);

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div
        aria-live="polite"
        className="fixed top-4 right-4 z-[100] flex flex-col gap-2 w-[min(340px,calc(100vw-2rem))]"
      >
        {toasts.map((toast) => (
          <ToastCard key={toast.id} toast={toast} onDismiss={() => dismiss(toast.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
};

const TONE_STYLES: Record<ToastTone, string> = {
  success: "border-status-success/40 text-status-success",
  error: "border-status-critical/40 text-status-critical",
  warning: "border-status-warning/40 text-status-warning",
  info: "border-accent-primary/40 text-accent-primary",
};

const ToastCard: React.FC<{ toast: Toast; onDismiss: () => void }> = ({ toast, onDismiss }) => (
  <button
    type="button"
    onClick={onDismiss}
    className={`animate-slide-in-right text-left bg-app-surface-raised border px-4 py-3 rounded-xl shadow-raised text-sm font-medium cursor-pointer hover:brightness-110 transition ${TONE_STYLES[toast.tone]}`}
  >
    {toast.message}
  </button>
);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within <ToastProvider>");
  }
  return ctx;
}
