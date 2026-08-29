import { useEffect, useRef, useState, useCallback } from "react";
import { requestStreamTicket, streamUrl } from "../api/streamApi";

export type LiveAlert = {
  id: number;
  source?: string;
  source_ip?: string | null;
  severity?: string;
  message?: string;
  created_at?: string | null;
  org_id?: number | null;
};

export type StreamStatus = "connecting" | "live" | "reconnecting" | "offline";

interface UseAlertStreamOptions {
  onAlert: (alert: LiveAlert) => void;
  onGap?: (info: { dropped: number }) => void;
  enabled?: boolean;
}

const MAX_BACKOFF = 30000;
const INITIAL_BACKOFF = 1000;

/**
 * Opens an SSE stream with a freshly minted ticket.
 * - No JWT in URL (ticket is single-use, 30s TTL)
 * - Reconnects with a NEW ticket (old one is spent)
 * - Reports gap when server says events were dropped
 * - Honest status: live / reconnecting / offline
 */
export const useAlertStream = ({ onAlert, onGap, enabled = true }: UseAlertStreamOptions) => {
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const esRef = useRef<EventSource | null>(null);
  const backoffRef = useRef(INITIAL_BACKOFF);
  const retryTimerRef = useRef<number | null>(null);
  const mountedRef = useRef(true);

  const cleanup = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    if (retryTimerRef.current) {
      window.clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, []);

  const connect = useCallback(async () => {
    if (!enabled || !mountedRef.current) return;
    setStatus("connecting");
    try {
      const ticket = await requestStreamTicket();
      if (!mountedRef.current) return;
      const url = streamUrl(ticket);
      const es = new EventSource(url);
      esRef.current = es;

      es.addEventListener("ready", () => {
        if (!mountedRef.current) return;
        backoffRef.current = INITIAL_BACKOFF;
        setStatus("live");
      });

      es.addEventListener("alert", (event: MessageEvent) => {
        try {
          const data = JSON.parse((event as any).data);
          onAlert(data as LiveAlert);
        } catch {
          // ignore malformed frame
        }
      });

      es.addEventListener("gap", (event: MessageEvent) => {
        try {
          const data = JSON.parse((event as any).data);
          onGap?.(data);
        } catch {
          onGap?.({ dropped: 0 });
        }
      });

      es.onerror = () => {
        es.close();
        esRef.current = null;
        if (!mountedRef.current) return;
        setStatus("reconnecting");
        const delay = backoffRef.current;
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF);
        retryTimerRef.current = window.setTimeout(() => {
          connect();
        }, delay) as unknown as number;
      };
    } catch {
      if (!mountedRef.current) return;
      setStatus("reconnecting");
      const delay = backoffRef.current;
      backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF);
      retryTimerRef.current = window.setTimeout(() => {
        connect();
      }, delay) as unknown as number;
    }
  }, [enabled, onAlert, onGap]);

  useEffect(() => {
    mountedRef.current = true;
    if (enabled) {
      connect();
    } else {
      setStatus("offline");
    }
    return () => {
      mountedRef.current = false;
      cleanup();
    };
  }, [enabled, connect, cleanup]);

  return { status, live: status === "live" };
};
