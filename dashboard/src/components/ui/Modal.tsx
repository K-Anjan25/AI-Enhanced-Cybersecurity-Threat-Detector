/**
 * Modal / ConfirmDialog — design.md §6: "focus trap, `Esc` to close, returns focus
 * to the trigger; destructive confirms require typing the target name".
 *
 * Four behaviours, each of which is a way a hand-rolled dialog fails:
 *
 *   * **focus moves in** on open, to the first focusable control, so the keyboard
 *     user is not left behind the overlay;
 *   * **focus stays in** — `Tab` and `Shift+Tab` wrap inside the dialog, because a
 *     trap that only intercepts `Tab` lets the user escape backwards;
 *   * **`Esc` closes**, the one keyboard route that must work even when the dialog
 *     has no buttons of its own;
 *   * **focus returns to the trigger** on close, so the operator resumes where they
 *     were rather than at the top of the page.
 *
 * `ConfirmDialog` adds the destructive rule: the confirming button stays disabled
 * until the target's name is typed *exactly*. It is a separate component rather
 * than a prop of `Modal`, so a caller who means to be destructive cannot forget it.
 * The gate is plain React state — a `disabled` attribute poked at from an event
 * handler would not survive the next render.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';

import { Button } from './Button';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** A readable, stable id for the heading a dialog is labelled by. */
function titleId(title: string): string {
  return `modal-${title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')}`;
}

export interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** Controls for the dialog's footer, usually Buttons. */
  footer?: ReactNode;
}

export function Modal({ open, title, onClose, children, footer }: ModalProps) {
  const dialog = useRef<HTMLDivElement | null>(null);
  const trigger = useRef<Element | null>(null);

  // Remember what had focus, move focus in, and give it back on close. The trigger
  // is captured on the *open* edge: by the time the cleanup runs, focus has already
  // moved into the dialog.
  useEffect(() => {
    if (!open) return undefined;
    trigger.current = document.activeElement;
    const first = dialog.current?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? dialog.current)?.focus();
    return () => {
      if (trigger.current instanceof HTMLElement) trigger.current.focus();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;
      const focusable = [...(dialog.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])];
      const first = focusable[0];
      const last = focusable.at(-1);
      if (first === undefined || last === undefined) return;
      const active = document.activeElement;
      if (event.shiftKey && (active === first || active === dialog.current)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="scrim fixed inset-0 z-50 flex items-center justify-center p-6">
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId(title)}
        tabIndex={-1}
        // The only shadow in the system: overlays get elevation, cards do not
        // (design.md §5.5).
        className="w-full max-w-xl rounded-modal border border-line bg-surface p-4 shadow-overlay"
      >
        <h2 id={titleId(title)} className="text-h2">
          {title}
        </h2>
        <div className="mt-4 text-body text-ink">{children}</div>
        {footer === undefined ? null : <div className="mt-4 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
}

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  /** What will happen, in plain language. */
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  /**
   * The name of the thing being destroyed. When set, confirming requires typing it
   * exactly — the safeguard design.md §6 asks for on destructive actions.
   */
  confirmPhrase?: string | undefined;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  onConfirm,
  onClose,
  confirmPhrase,
}: ConfirmDialogProps) {
  const [typed, setTyped] = useState('');
  const needsPhrase = confirmPhrase !== undefined;

  // A stale confirmation must not survive into the next time the dialog opens.
  useEffect(() => {
    if (!open) setTyped('');
  }, [open]);

  const ready = !needsPhrase || typed === confirmPhrase;

  return (
    <Modal
      open={open}
      title={title}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" onClick={onConfirm} disabled={!ready}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p>{message}</p>
      {needsPhrase ? (
        <label className="mt-4 flex flex-col gap-2 text-body-sm text-muted">
          Type {confirmPhrase} to confirm
          <input
            type="text"
            value={typed}
            onChange={(event) => setTyped(event.currentTarget.value)}
            className="h-8 rounded-input border border-line bg-base px-3 text-body text-ink"
          />
        </label>
      ) : null}
    </Modal>
  );
}
