import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { expectAccessible } from '../../test/axe';
import { ConfirmDialog, Modal } from './Modal';

/** A dialog is only meaningful with a trigger, so the trigger is in the test too. */
function Harness({ onClose = () => {} }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Delete hunt
      </button>
      <Modal
        open={open}
        title="Delete saved hunt"
        onClose={() => {
          setOpen(false);
          onClose();
        }}
        footer={
          <>
            <button type="button" onClick={() => setOpen(false)}>
              Cancel
            </button>
            <button type="button">Delete</button>
          </>
        }
      >
        <p>Deleting a saved hunt cannot be undone.</p>
      </Modal>
    </>
  );
}

describe('Modal', () => {
  it('renders nothing until it is open', () => {
    render(
      <Modal open={false} title="Delete saved hunt" onClose={() => {}}>
        <p>hidden</p>
      </Modal>,
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('is a labelled modal dialog', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Delete hunt' }));

    const dialog = screen.getByRole('dialog', { name: 'Delete saved hunt' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    await expectAccessible(dialog);
  });

  it('moves focus into the dialog, and gives it back to the trigger', () => {
    render(<Harness />);
    const trigger = screen.getByRole('button', { name: 'Delete hunt' });

    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('closes on Escape', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: 'Delete hunt' }));

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('keeps Tab inside the dialog, forwards and backwards', () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Delete hunt' }));

    const cancel = screen.getByRole('button', { name: 'Cancel' });
    const confirm = screen.getByRole('button', { name: 'Delete' });

    confirm.focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(cancel).toHaveFocus();

    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(confirm).toHaveFocus();
  });
});

describe('ConfirmDialog', () => {
  function ConfirmHarness({ phrase }: { phrase?: string | undefined }) {
    const [open, setOpen] = useState(false);
    const [confirmed, setConfirmed] = useState(false);
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>
          Delete a model
        </button>
        {confirmed ? <p>model deleted</p> : null}
        <ConfirmDialog
          open={open}
          title="Delete model"
          message="Version 12 will stop serving traffic."
          confirmLabel="Delete model"
          confirmPhrase={phrase}
          onConfirm={() => {
            setConfirmed(true);
            setOpen(false);
          }}
          onClose={() => setOpen(false)}
        />
      </>
    );
  }

  it('refuses to confirm until the target name is typed exactly', () => {
    render(<ConfirmHarness phrase="fraud-v12" />);
    fireEvent.click(screen.getByRole('button', { name: 'Delete a model' }));

    const confirm = screen.getByRole('button', { name: 'Delete model' });
    const field = screen.getByRole('textbox');

    expect(confirm).toBeDisabled();

    fireEvent.change(field, { target: { value: 'fraud' } });
    expect(confirm).toBeDisabled();

    fireEvent.change(field, { target: { value: 'fraud-v12' } });
    expect(confirm).toBeEnabled();
  });

  it('locks again when the name is cleared — the gate is state, not an event', () => {
    // The regression this guards: a `disabled` attribute flipped by the event
    // handler and never flipped back would leave the dialog armed after a typo.
    render(<ConfirmHarness phrase="fraud-v12" />);
    fireEvent.click(screen.getByRole('button', { name: 'Delete a model' }));

    const confirm = screen.getByRole('button', { name: 'Delete model' });
    const field = screen.getByRole('textbox');

    fireEvent.change(field, { target: { value: 'fraud-v12' } });
    expect(confirm).toBeEnabled();

    fireEvent.change(field, { target: { value: 'fraud-v1' } });
    expect(confirm).toBeDisabled();
  });

  it('confirms, and hands control back to the caller', () => {
    render(<ConfirmHarness phrase="fraud-v12" />);
    fireEvent.click(screen.getByRole('button', { name: 'Delete a model' }));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'fraud-v12' } });

    // Scoped to the dialog: the trigger outside it has a different name, and this
    // is the difference between "the user confirmed" and "the user opened it again".
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete model' }),
    );

    expect(screen.getByText('model deleted')).toBeInTheDocument();
  });

  it('needs no typed phrase when the action is not destructive enough to require one', () => {
    render(<ConfirmHarness />);
    fireEvent.click(screen.getByRole('button', { name: 'Delete a model' }));

    expect(screen.getByRole('button', { name: 'Delete model' })).toBeEnabled();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('forgets a stale confirmation when it is reopened', () => {
    function ReopenHarness() {
      const [open, setOpen] = useState(true);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Reopen
          </button>
          <ConfirmDialog
            open={open}
            title="Delete model"
            message="Version 12 will stop serving traffic."
            confirmLabel="Delete model"
            confirmPhrase="fraud-v12"
            onConfirm={() => setOpen(false)}
            onClose={() => setOpen(false)}
          />
        </>
      );
    }
    render(<ReopenHarness />);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'fraud-v12' } });

    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.click(screen.getByRole('button', { name: 'Reopen' }));

    expect(screen.getByRole('button', { name: 'Delete model' })).toBeDisabled();
  });
});
