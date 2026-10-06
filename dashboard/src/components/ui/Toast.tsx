/**
 * Toast — design.md §6: "success / warning / error; auto-dismiss except errors".
 *
 * The whole contract is in that last clause, and it is a rule about who is allowed
 * to lose information. A success message is an acknowledgement: it can leave on its
 * own. A warning is a heads-up the analyst has already been shown. An error is a
 * failure — the thing the operator most needs to see is exactly the thing a timer
 * is most likely to take away, so an error stays until it is dismissed.
 *
 * `ToastProvider` renders the region and owns the timers; `useToast` is the only
 * way to raise one, so no component can render an unmanaged toast into the DOM and
 * skip the auto-dismiss rule. Each toast is its own live region: `role="alert"` for
 * errors (assertive) and `role="status"` for the rest (polite), which is what makes
 * the announcement differ from the visual persistence.
 *
 * Announcements carry the words, never the styling: there is no prop that puts
 * colour on a toast's message, so "success" is a phrase the analyst reads, not a
 * green border they have to interpret.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import { Button } from './Button';

export type ToastIntent = 'success' | 'warning' | 'error';

export interface ToastRecord {
  id: number;
  intent: ToastIntent;
  message: string;
}

/** How long a non-error toast stays. Long enough to read twice. */
export const DEFAULT_TOAST_MS = 6_000;

const RAISE = Symbol('aegis.toast');

type Raise = (intent: ToastIntent, message: string) => void;

const ToastContext = createContext<Raise | null>(null);

/** The heading each intent is announced with. Neutral words, no exclamation mark. */
const TITLES: Record<ToastIntent, string> = {
  success: 'Done',
  warning: 'Warning',
  error: 'Error',
};

/** Errors stay until dismissed; everything else leaves on its own. */
function autoDismisses(intent: ToastIntent): boolean {
  return intent !== 'error';
}

export interface ToastProviderProps {
  children: ReactNode;
  /** Override the auto-dismiss delay, in milliseconds. Applies to non-errors. */
  duration?: number;
}

export function ToastProvider({ children, duration = DEFAULT_TOAST_MS }: ToastProviderProps) {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Set<ReturnType<typeof setTimeout>>());

  // One timer per toast, all tracked, so unmounting the provider (a route change,
  // a test teardown) cannot leave a timer that fires into a dead component.
  useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const timer of pending) clearTimeout(timer);
      pending.clear();
    };
  }, []);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const raise = useCallback<Raise>(
    (intent, message) => {
      const id = nextId.current++;
      setToasts((current) => [...current, { id, intent, message }]);
      if (!autoDismisses(intent)) return;
      const timer = setTimeout(() => {
        timers.current.delete(timer);
        dismiss(id);
      }, duration);
      timers.current.add(timer);
    },
    [dismiss, duration],
  );

  const context = useMemo(() => raise, [raise]);

  return (
    <ToastContext.Provider value={context}>
      {children}
      <div
        role="region"
        aria-label="Notifications"
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-full max-w-xl flex-col gap-2"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role={toast.intent === 'error' ? 'alert' : 'status'}
            className="pointer-events-auto flex items-start justify-between gap-4 rounded-card border border-line bg-surface p-4 shadow-overlay"
          >
            <p className="text-body-sm text-ink">
              <span className="font-semibold">{TITLES[toast.intent]}: </span>
              {toast.message}
            </p>
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Dismiss ${TITLES[toast.intent].toLowerCase()} notification`}
              onClick={() => dismiss(toast.id)}
            >
              Dismiss
            </Button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/**
 * Raise a toast. Throws outside a provider rather than dropping the message: a
 * notification that silently goes nowhere is worse than a crash in development.
 */
export function useToast(): Raise {
  const raise = useContext(ToastContext);
  if (raise === null || typeof raise !== 'function') {
    throw new Error(`${String(RAISE)} useToast must be called inside a ToastProvider`);
  }
  return raise;
}
