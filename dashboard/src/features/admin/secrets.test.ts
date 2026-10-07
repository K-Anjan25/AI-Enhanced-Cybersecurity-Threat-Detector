/**
 * The one-time rule for a secret the API issues (T-313's API key, T-422's signing
 * secret).
 *
 * The predicate is four lines and every one of them is a case a screenshot cannot
 * show: a dialog that looks identical whether its field holds a live secret or
 * nothing. The negative ones are the whole point — a capture from a *later* rendering,
 * and a closed dialog, must both refuse.
 */
import { describe, expect, it } from 'vitest';

import { secretIsLive, type IssuedSecret } from './secrets';

const CAPTURE: IssuedSecret = { secret: 'aegis_sk_7_deadbeef', expiresWith: 3 }; // pragma: allowlist secret

describe('secretIsLive', () => {
  it('is live for the rendering that captured it', () => {
    expect(secretIsLive(CAPTURE, 3)).toBe(true);
  });

  it('is not live for a later rendering', () => {
    // Bumping the counter is the sequence that would otherwise leave a secret on
    // screen in a reopened dialog.
    expect(secretIsLive(CAPTURE, 4)).toBe(false);
  });

  it('is not live when the dialog is closed, whatever the counter says', () => {
    // A closed panel passes `null`, which is what makes the secret unreachable by
    // construction rather than by a caller remembering to clear a field.
    expect(secretIsLive(CAPTURE, null)).toBe(false);
  });

  it('is not live when there is no capture at all', () => {
    expect(secretIsLive(null, 3)).toBe(false);
    expect(secretIsLive(null, null)).toBe(false);
  });
});
