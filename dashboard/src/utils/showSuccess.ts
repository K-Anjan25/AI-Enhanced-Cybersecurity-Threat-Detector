/**
 * Non-blocking success notification.
 *
 * Renders an auto-dismissing toast (no modal/alert), so repeated actions never
 * trap the user behind a blocking popup. Follows the SOC design tokens.
 */

const TOAST_MS = 3500;

interface ToastElement {
  el: HTMLDivElement;
  timer: number;
}

const toasts: ToastElement[] = [];

function dismiss(el: HTMLDivElement, timer: number): void {
  el.style.transition = "opacity 200ms ease";
  el.style.opacity = "0";
  window.setTimeout(() => {
    el.remove();
    const index = toasts.findIndex((t) => t.el === el);
    if (index >= 0) toasts.splice(index, 1);
  }, 220);
  window.clearTimeout(timer);
}

export const showSuccess = (message: string): void => {
  console.log(`[SOC SUCCESS]: ${message}`);

  const el = document.createElement("div");
  el.setAttribute("role", "status");
  el.setAttribute("aria-live", "polite");
  el.style.position = "fixed";
  el.style.top = "20px";
  el.style.right = "20px";
  el.style.zIndex = "9999";
  el.style.maxWidth = "340px";
  el.style.padding = "12px 16px";
  el.style.borderRadius = "10px";
  el.style.fontSize = "13px";
  el.style.lineHeight = "1.4";
  el.style.boxShadow = "0 10px 30px rgba(0,0,0,0.45)";
  el.style.backgroundColor = "#0f172a";
  el.style.border = "1px solid rgba(52, 211, 153, 0.35)";
  el.style.color = "#34d399";
  el.textContent = message;

  el.addEventListener("click", () => {
    const current = toasts.find((t) => t.el === el);
    if (current) dismiss(current.el, current.timer);
  });

  document.body.appendChild(el);
  const timer = window.setTimeout(() => {
    const current = toasts.find((t) => t.el === el);
    if (current) dismiss(current.el, current.timer);
  }, TOAST_MS);
  toasts.push({ el, timer });
};

export default showSuccess;