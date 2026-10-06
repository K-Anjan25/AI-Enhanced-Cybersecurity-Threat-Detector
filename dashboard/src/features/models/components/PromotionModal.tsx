/**
 * The promotion modal (design.md §4.7, FR-33).
 *
 * The design's safeguard is the point of this file: *"a modal with an explicit
 * confirm typing the model ID"*. Three properties make it a safeguard rather than a
 * speed bump, and each is tested:
 *
 *   * **The typed id must match exactly.** `promotionReadiness` applies
 *     `ConfirmDialog`'s rule (T-402) — equality, no trimming, no case folding — and
 *     the control stays disabled until it holds. An operator promoting one of two
 *     versions that differ in a character gets no help from a fuzzy match.
 *   * **The justification is required, and the API agrees.** The server's
 *     `PromotionRequest` has `min_length=1`, so an empty one is a 422; the modal
 *     refuses to send it rather than letting the server explain it.
 *   * **What will happen is stated before it happens.** The incumbent is named: a
 *     promotion retires whatever is serving for the kind (T-315), and an operator who
 *     did not know that would be surprised by a model they never mentioned.
 *
 * A refusal from the server is rendered inside the dialog, where the operator is
 * still looking, rather than only as a toast that disappears.
 */
import { useEffect, useState } from 'react';

import { Button, Modal } from '../../../components/ui';
import type { VersionRow } from '../versions';
import { MAX_REASON_LENGTH, promotionReadiness, shortId } from '../versions';

export interface PromotionModalProps {
  open: boolean;
  /** The version under consideration, or `null` when nothing is selected. */
  row: VersionRow | null;
  /** The version currently serving the same kind, named so the change is explicit. */
  incumbent: VersionRow | null;
  pending: boolean;
  /** The server's refusal, already mapped to a sentence. `null` while none. */
  refusal: string | null;
  onClose: () => void;
  onSubmit: (modelId: string, justification: string) => void;
}

export function PromotionModal({
  open,
  row,
  incumbent,
  pending,
  refusal,
  onClose,
  onSubmit,
}: PromotionModalProps) {
  const [typedId, setTypedId] = useState('');
  const [justification, setJustification] = useState('');

  // A confirmation must not survive into the next time the dialog opens: a stale
  // typed id would confirm a different version with one keystroke (T-402's rule).
  useEffect(() => {
    if (!open) {
      setTypedId('');
      setJustification('');
    }
  }, [open]);

  if (row === null) return null;

  const readiness = promotionReadiness({
    typedId,
    modelId: row.id,
    justification,
  });

  return (
    <Modal
      open={open}
      title={`Promote ${shortId(row.id)}`}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              onSubmit(row.id, justification.trim());
            }}
            disabled={!readiness.ready}
            loading={pending}
            title={readiness.reason ?? undefined}
          >
            Promote to active
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3 text-body">
        <p>
          This makes the version active and retires whatever is serving{' '}
          {row.kindLabel.toLowerCase()} traffic, in one call (FR-33).{' '}
          {incumbent === null
            ? 'Nothing is serving this kind at the moment, so nothing steps down.'
            : `Currently serving: ${incumbent.shortId}, which will step down.`}
        </p>
        <p className="text-body-sm text-muted">
          The version id is <code className="font-mono">{row.id}</code>.
        </p>
        {/*
          design.md §4.7 asks for shadow-mode as the *default promotion target*, and
          this registry has no `shadow` status (D-047 names the gap). Promoting here
          goes straight to active, so the dialog says that rather than letting an
          operator assume a shadow period the API cannot give them.
        */}
        <p className="text-body-sm text-muted">
          Shadow scoring happens in the harness before a version is promoted (T-213); this registry
          has no <code className="font-mono">shadow</code> status, so this promotion goes straight
          to active.
        </p>

        <label className="flex flex-col gap-2 text-body-sm">
          Justification (required)
          <textarea
            value={justification}
            maxLength={MAX_REASON_LENGTH}
            rows={3}
            onChange={(event) => {
              setJustification(event.currentTarget.value);
            }}
            className="rounded-input border border-line bg-base px-3 py-2 text-body text-ink"
          />
        </label>

        <label className="flex flex-col gap-2 text-body-sm">
          Type the model id to confirm
          <input
            type="text"
            value={typedId}
            onChange={(event) => {
              setTypedId(event.currentTarget.value);
            }}
            aria-describedby="promotion-confirm-hint"
            className="h-8 rounded-input border border-line bg-base px-3 font-mono text-body-sm text-ink"
          />
        </label>
        <p id="promotion-confirm-hint" className="text-body-sm text-muted">
          {readiness.reason ?? 'The id matches. Promote to make this version serve.'}
        </p>

        {refusal === null ? null : (
          <p role="alert" className="text-body-sm text-severityText-critical">
            {refusal}
          </p>
        )}
      </div>
    </Modal>
  );
}
