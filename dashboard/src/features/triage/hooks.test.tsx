/**
 * The triage screen's shortcut hooks, at the hook's own boundary.
 *
 * `TriagePage.test.tsx` asserts what the analyst sees when a key is pressed; this
 * file asserts what the hook *decides*, because two of the rules cannot be observed
 * through the page at all:
 *
 *   * **`enabled` is a real gate.** On an empty queue `stepHref` already refuses to
 *     produce an address, so a page test passes whether or not the hook checks the
 *     flag. The hook's contract is "do not call `onStep` when the screen says there
 *     is nowhere to step", and that is what is pinned here.
 *   * **A consumed keystroke is claimed.** `preventDefault` is invisible in the
 *     rendered output but is the difference between "j" and the browser's own
 *     behaviour on the same key.
 *
 * The three rules the hook shares with the verdict shortcuts — a repeat, a modified
 * keystroke and a keystroke inside a field are not shortcuts — are pinned here once
 * for the queue step; `lib/keyboard.test.ts` pins the pure decision they both call.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { useQueueShortcuts } from './hooks';

/** A screen with nothing but the hook and a field, so a keystroke's owner is clear. */
function Harness({ enabled, onStep }: { enabled: boolean; onStep: (delta: -1 | 1) => void }) {
  useQueueShortcuts(enabled, onStep);
  return <input aria-label="Note" />;
}

describe('useQueueShortcuts', () => {
  it('steps forward on j and back on k', async () => {
    const user = userEvent.setup();
    const onStep = vi.fn();
    render(<Harness enabled onStep={onStep} />);

    await user.keyboard('j');
    await user.keyboard('k');

    expect(onStep.mock.calls).toEqual([[1], [-1]]);
  });

  it('steps nothing when the screen says the queue has no rows', async () => {
    const user = userEvent.setup();
    const onStep = vi.fn();
    render(<Harness enabled={false} onStep={onStep} />);

    await user.keyboard('jk');

    expect(onStep).not.toHaveBeenCalled();
  });

  it('leaves the keystroke to the field it landed in', async () => {
    const user = userEvent.setup();
    const onStep = vi.fn();
    render(<Harness enabled onStep={onStep} />);

    await user.click(screen.getByRole('textbox', { name: 'Note' }));
    await user.keyboard('jk');

    expect(onStep).not.toHaveBeenCalled();
  });

  it('refuses a repeat and a modified keystroke', () => {
    const onStep = vi.fn();
    render(<Harness enabled onStep={onStep} />);

    fireEvent.keyDown(window, { key: 'j', repeat: true });
    fireEvent.keyDown(window, { key: 'j', ctrlKey: true });
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    fireEvent.keyDown(window, { key: 'k', altKey: true });
    fireEvent.keyDown(window, { key: 'k', shiftKey: true });

    expect(onStep).not.toHaveBeenCalled();
  });

  it('claims the keystroke it consumes, so the browser does not act on it too', () => {
    render(<Harness enabled onStep={() => {}} />);
    const event = new KeyboardEvent('keydown', { key: 'j', cancelable: true });

    window.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
  });

  it('listens only while it is mounted', () => {
    const onStep = vi.fn();
    const { unmount } = render(<Harness enabled onStep={onStep} />);

    unmount();
    fireEvent.keyDown(window, { key: 'j' });

    expect(onStep).not.toHaveBeenCalled();
  });
});
