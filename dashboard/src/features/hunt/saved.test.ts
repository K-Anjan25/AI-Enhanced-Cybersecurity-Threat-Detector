/**
 * Saved and recent hunts, against a real `localStorage`.
 *
 * The namespace is the case worth being explicit about: the subject comes out of an
 * *unverified* token, and the tests say so — two subjects do not see each other's
 * hunts, but a token that cannot be decoded lands in the same drawer as no token at
 * all, which is the honest description of a label rather than a boundary.
 *
 * Storage that refuses to work (private mode, a full quota) must not take the screen
 * with it: every function here is asserted to behave as if the list were empty rather
 * than to throw.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  clearRecentHunts,
  huntStoreSubject,
  recentHunts,
  rememberHunt,
  removeHunt,
  saveHunt,
  savedHunts,
  RECENT_LIMIT,
  SAVED_KEY,
  SAVED_LIMIT,
} from './saved';

const AT = new Date('2026-10-06T10:00:00Z');

/** A JWT-shaped token whose payload is the given claims. `atob` does not verify it. */
function token(claims: Record<string, unknown>): string {
  const encode = (value: unknown): string =>
    btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return `${encode({ alg: 'none' })}.${encode(claims)}.signature`;
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('huntStoreSubject', () => {
  it('reads `sub` out of the token without verifying it', () => {
    expect(huntStoreSubject(token({ sub: 'analyst-7' }))).toBe('analyst-7');
  });

  it('falls back to `local` when there is no session, or the token is a shape it cannot read', () => {
    expect(huntStoreSubject(null)).toBe('local');
    expect(huntStoreSubject('')).toBe('local');
    expect(huntStoreSubject('not-a-jwt')).toBe('local');
    expect(huntStoreSubject('a.%%%.c')).toBe('local');
    expect(huntStoreSubject(token({}))).toBe('local');
    expect(huntStoreSubject(token({ sub: 42 }))).toBe('local');
  });

  it('namespaces one subject’s hunts away from another’s', () => {
    saveHunt('analyst-7', 'lateral movement', 'family:lateral', AT);
    expect(savedHunts('analyst-7')).toHaveLength(1);
    expect(savedHunts('someone-else')).toEqual([]);
    // The key is per subject, so the same browser profile can hold both.
    expect(window.localStorage.getItem(`${SAVED_KEY}.analyst-7`)).not.toBeNull();
    expect(window.localStorage.getItem(`${SAVED_KEY}.someone-else`)).toBeNull();
  });
});

describe('saveHunt', () => {
  it('saves newest first, with the instant it was saved', () => {
    saveHunt('s', 'first', 'status:open', AT);
    saveHunt('s', 'second', 'status:closed', new Date('2026-10-06T11:00:00Z'));

    expect(savedHunts('s').map((entry) => entry.name)).toEqual(['second', 'first']);
    expect(savedHunts('s')[1]?.savedAt).toBe('2026-10-06T10:00:00.000Z');
  });

  it('replaces a hunt of the same name rather than keeping both', () => {
    saveHunt('s', 'quiet sweep', 'severity:low', AT);
    saveHunt('s', 'quiet sweep', 'severity:low status:open', AT);

    const saved = savedHunts('s');
    expect(saved).toHaveLength(1);
    expect(saved[0]?.text).toBe('severity:low status:open');
  });

  it('trims the name and the text, and refuses an empty either', () => {
    expect(saveHunt('s', '   ', 'status:open', AT)).toEqual([]);
    expect(saveHunt('s', 'named', '   ', AT)).toEqual([]);
    expect(saveHunt('s', '  named  ', '  status:open  ', AT)[0]).toEqual({
      name: 'named',
      text: 'status:open',
      savedAt: AT.toISOString(),
    });
  });

  it('caps how many one browser holds', () => {
    for (let index = 0; index < SAVED_LIMIT + 5; index += 1) {
      saveHunt('s', `hunt-${String(index)}`, 'status:open', AT);
    }
    expect(savedHunts('s')).toHaveLength(SAVED_LIMIT);
    // Newest wins: the cap drops the oldest, not the newest.
    expect(savedHunts('s')[0]?.name).toBe(`hunt-${String(SAVED_LIMIT + 4)}`);
  });
});

describe('removeHunt', () => {
  it('forgets one by name and leaves the rest', () => {
    saveHunt('s', 'keep', 'status:open', AT);
    saveHunt('s', 'drop', 'status:closed', AT);

    expect(removeHunt('s', 'drop').map((entry) => entry.name)).toEqual(['keep']);
    // Through the store, not just the return value.
    expect(savedHunts('s').map((entry) => entry.name)).toEqual(['keep']);
  });
});

describe('rememberHunt', () => {
  it('records the newest first', () => {
    rememberHunt('s', 'status:open', AT);
    rememberHunt('s', 'status:closed', AT);
    expect(recentHunts('s').map((entry) => entry.text)).toEqual(['status:closed', 'status:open']);
  });

  it('deduplicates by text, so re-running moves a hunt up instead of stacking it', () => {
    rememberHunt('s', 'status:open', AT);
    rememberHunt('s', 'status:closed', AT);
    rememberHunt('s', 'status:open', new Date('2026-10-06T12:00:00Z'));

    const recent = recentHunts('s');
    expect(recent.map((entry) => entry.text)).toEqual(['status:open', 'status:closed']);
    expect(recent[0]?.at).toBe('2026-10-06T12:00:00.000Z');
  });

  it('caps the list, dropping the oldest', () => {
    for (let index = 0; index < RECENT_LIMIT + 3; index += 1) {
      rememberHunt('s', `q${String(index)}`, AT);
    }
    expect(recentHunts('s')).toHaveLength(RECENT_LIMIT);
    expect(recentHunts('s').at(-1)?.text).toBe('q3');
  });

  it('ignores an empty query — a blank run is not a hunt worth remembering', () => {
    expect(rememberHunt('s', '   ', AT)).toEqual([]);
  });
});

describe('clearRecentHunts', () => {
  it('empties the list but keeps the saved ones', () => {
    saveHunt('s', 'kept', 'status:open', AT);
    rememberHunt('s', 'status:open', AT);

    clearRecentHunts('s');

    expect(recentHunts('s')).toEqual([]);
    expect(savedHunts('s')).toHaveLength(1);
  });
});

describe('storage that does not work', () => {
  it('keeps the list for the session and throws nothing when localStorage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('access denied');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded');
    });

    expect(savedHunts('s')).toEqual([]);
    expect(recentHunts('s')).toEqual([]);
    // The functions return the list the caller should render, and the caller's state
    // is the session's list: an unwritable store means the hunt is not *remembered*,
    // not that the analyst watches their own save fail with no explanation.
    expect(saveHunt('s', 'named', 'status:open', AT).map((entry) => entry.name)).toEqual(['named']);
    expect(rememberHunt('s', 'status:open', AT).map((entry) => entry.text)).toEqual([
      'status:open',
    ]);
    // Nothing reached the store, so a reload starts empty — which is what "not
    // remembered" means, and the screen says the list is per browser.
    expect(window.localStorage.length).toBe(0);
    expect(() => clearRecentHunts('s')).not.toThrow();
  });

  it('reads a corrupt entry as an empty list rather than throwing on every mount', () => {
    window.localStorage.setItem(`${SAVED_KEY}.s`, '{not json');
    expect(savedHunts('s')).toEqual([]);
  });

  it('drops entries that are not the shape it wrote', () => {
    window.localStorage.setItem(
      `${SAVED_KEY}.s`,
      JSON.stringify([
        { name: 'good', text: 'status:open', savedAt: AT.toISOString() },
        { name: 1 },
        'nonsense',
      ]),
    );
    expect(savedHunts('s').map((entry) => entry.name)).toEqual(['good']);
  });
});
