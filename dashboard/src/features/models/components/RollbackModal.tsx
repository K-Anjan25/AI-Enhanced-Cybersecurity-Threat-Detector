/**
 * The rollback dialog (FR-33).
 *
 * A rollback names a **kind**, not a version: the server finds the version the
 * active one displaced (T-315), so an operator cannot roll back to something that
 * never served. That is why this dialog has no version picker — offering one would
 * imply a capability the API deliberately does not have.
 *
 * The reason is required because the server requires it, and because a rollback
 * without a stated reason is an unexplained change in a trail nobody can edit
 * (D-041).
 */
import { useEffect, useState } from 'react';

import { Button, Modal } from '../../../components/ui';
import { MAX_REASON_LENGTH } from '../versions';

export interface RollbackModalProps {
  open: boolean;
  /** The kind being rolled back, or `null` when nothing is selected. */
  kind: string | null;
  kindLabel: string;
  pending: boolean;
  /** The server's refusal, already mapped to a sentence. `null` while none. */
  refusal: string | null;
  onClose: () => void;
  onSubmit: (kind: string, reason: string) => void;
}

export function RollbackModal({
  open,
  kind,
  kindLabel,
  pending,
  refusal,
  onClose,
  onSubmit,
}: RollbackModalProps) {
  const [reason, setReason] = useState('');

  useEffect(() => {
    if (!open) setReason('');
  }, [open]);

  if (kind === null) return null;

  return (
    <Modal
      open={open}
      title={`Roll back ${kindLabel.toLowerCase()} serving`}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              onSubmit(kind, reason.trim());
            }}
            disabled={reason.trim() === ''}
            loading={pending}
          >
            Roll back
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3 text-body">
        <p>
          This reverses the most recent {kindLabel.toLowerCase()} promotion: the version that
          stepped down becomes active again. Retired stays terminal for every other version (R-68),
          and each promotion can be rolled back once.
        </p>
        <label className="flex flex-col gap-2 text-body-sm">
          Reason (required)
          <textarea
            value={reason}
            maxLength={MAX_REASON_LENGTH}
            rows={3}
            onChange={(event) => {
              setReason(event.currentTarget.value);
            }}
            className="rounded-input border border-line bg-base px-3 py-2 text-body text-ink"
          />
        </label>
        {refusal === null ? null : (
          <p role="alert" className="text-body-sm text-severityText-critical">
            {refusal}
          </p>
        )}
      </div>
    </Modal>
  );
}
