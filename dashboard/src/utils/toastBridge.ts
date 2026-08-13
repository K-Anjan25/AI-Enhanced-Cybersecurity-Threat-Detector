import { useToast, ToastProvider, ToastTone } from "../components/ui/Toast";

/**
 * Registry bridge so non-React call sites (e.g. `showSuccess`/`showError`
 * utils) can push toasts. The provider registers itself; while it is not yet
 * mounted, calls degrade to a console log (which is also the double-click
 * safety in dev StrictMode).
 */
export function useAppToast(): { push: (message: string, tone?: ToastTone) => void } {
  const toast = useToast();
  return toast;
}

export { ToastProvider };
export type { ToastTone };