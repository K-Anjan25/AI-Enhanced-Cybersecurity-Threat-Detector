import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  clearSessionToken,
  onSessionTokenChange,
  refreshToken,
  resetSessionForTests,
  SESSION_REFRESH_TOKEN_KEY,
  SESSION_TOKEN_KEY,
  sessionToken,
  setSessionCredentials,
  setSessionToken,
} from './session';

afterEach(() => {
  resetSessionForTests();
});

describe('the session token', () => {
  it('is absent until something signs in', () => {
    expect(sessionToken()).toBeNull();
  });

  it('picks up a credential left behind by an earlier page load', () => {
    resetSessionForTests();
    window.sessionStorage.setItem(SESSION_TOKEN_KEY, 't-from-storage');

    expect(sessionToken()).toBe('t-from-storage');
  });

  it('lives in session storage, not local storage', () => {
    // A token that outlives the tab is a token on a shared workstation at the end
    // of the day; the theme preference may persist, a credential may not.
    setSessionToken('t-1');

    expect(window.sessionStorage.getItem(SESSION_TOKEN_KEY)).toBe('t-1');
    expect(window.localStorage.getItem(SESSION_TOKEN_KEY)).toBeNull();
  });

  it('stores access and refresh credentials in tab-scoped storage only', () => {
    setSessionCredentials('access-1', 'refresh-1');

    expect(sessionToken()).toBe('access-1');
    expect(refreshToken()).toBe('refresh-1');
    expect(window.sessionStorage.getItem(SESSION_TOKEN_KEY)).toBe('access-1');
    expect(window.sessionStorage.getItem(SESSION_REFRESH_TOKEN_KEY)).toBe('refresh-1');
    expect(window.localStorage.getItem(SESSION_REFRESH_TOKEN_KEY)).toBeNull();
  });

  it('clears both credentials when the session ends', () => {
    setSessionCredentials('access-1', 'refresh-1');

    clearSessionToken();

    expect(sessionToken()).toBeNull();
    expect(refreshToken()).toBeNull();
    expect(window.sessionStorage.getItem(SESSION_REFRESH_TOKEN_KEY)).toBeNull();
  });

  it('treats an empty or blank token as no session at all', () => {
    setSessionToken('t-1');

    setSessionToken('');
    expect(sessionToken()).toBeNull();

    setSessionToken('   ');
    expect(sessionToken()).toBeNull();
  });

  it('trims what it is given, so a padded copy still authenticates', () => {
    setSessionToken('  t-2  ');

    expect(sessionToken()).toBe('t-2');
  });

  it('tells the socket whenever the credential changes', () => {
    const seen: (string | null)[] = [];
    const unsubscribe = onSessionTokenChange((token) => seen.push(token));

    setSessionToken('t-1');
    setSessionToken('t-2');
    clearSessionToken();

    expect(seen).toEqual(['t-1', 't-2', null]);

    unsubscribe();
    setSessionToken('t-3');
    expect(seen).toEqual(['t-1', 't-2', null]);
  });

  it('announces a re-issued credential even when it is the same string', () => {
    // Revoking and reissuing produce the same bytes only by accident, and a socket
    // that kept its old authority because the string matched is not a state
    // anybody asked for.
    const seen: (string | null)[] = [];
    const unsubscribe = onSessionTokenChange((token) => seen.push(token));

    setSessionToken('t-1');
    setSessionToken('t-1');

    expect(seen).toEqual(['t-1', 't-1']);
    unsubscribe();
  });

  it('clears without announcing when there was nothing to clear', () => {
    const listener = vi.fn();
    onSessionTokenChange(listener);

    clearSessionToken();

    expect(listener).not.toHaveBeenCalled();
  });
});
