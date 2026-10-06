/**
 * Saved and recent hunts (T-408, design.md §4.6: "saved queries per user; recent
 * queries in a dropdown").
 *
 * **"Per user" is per browser in this build, and the screen says so.** There is no
 * sign-in yet (T-417) and no server-side store for a named query, so the honest
 * place for one is `localStorage`. The store is keyed by the token's `sub` when a
 * session exists, which is a *label* and not a security boundary: the token is not
 * verified here, and two analysts sharing a browser profile without signing in
 * share each other's saved hunts. Naming that on the screen is the point — a saved
 * hunt that silently belonged to someone else would be a quiet data leak.
 *
 * **Recent hunts are recorded on a successful read, not on every keystroke.** A
 * dropdown of half-typed queries is noise, and the list is deduplicated by text so
 * re-running the same hunt moves it to the top rather than filling the list.
 *
 * Everything here is defensive about storage: a browser in private mode throws on
 * access, and a dashboard that crashed because it could not remember a query would
 * be trading a real feature for a convenience one.
 */

/** Where saved hunts live. Not a credential, so `localStorage` rather than the session. */
export const SAVED_KEY = 'aegis.hunt.saved';
export const RECENT_KEY = 'aegis.hunt.recent';

/** How many recent hunts the dropdown keeps. */
export const RECENT_LIMIT = 8;

/** How many saved hunts one browser holds, so the store cannot grow without bound. */
export const SAVED_LIMIT = 50;

export interface SavedHunt {
  name: string;
  text: string;
  /** When it was last saved, ISO-8601. Shown in the list, so it is written down. */
  savedAt: string;
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/**
 * The store's namespace for the current session.
 *
 * The subject is read out of the token without verification: it selects a drawer,
 * it does not authorise anything, and the server is what enforces who may search.
 * An undecodable token is `local`, which is also what no session at all produces.
 */
export function huntStoreSubject(token: string | null): string {
  if (token === null || token === '') return 'local';
  const payload = token.split('.')[1];
  if (payload === undefined) return 'local';
  try {
    const claims = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/'))) as {
      sub?: unknown;
    };
    return typeof claims.sub === 'string' && claims.sub !== '' ? claims.sub : 'local';
  } catch {
    return 'local';
  }
}

function read<T>(key: string, subject: string): T[] {
  const store = storage();
  if (store === null) return [];
  try {
    const raw = store.getItem(`${key}.${subject}`);
    if (raw === null) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    // Unreadable or corrupt: an empty list is the honest answer, and the next save
    // overwrites it rather than throwing every time the screen mounts.
    return [];
  }
}

function write(key: string, subject: string, value: unknown[]): void {
  const store = storage();
  if (store === null) return;
  try {
    store.setItem(`${key}.${subject}`, JSON.stringify(value));
  } catch {
    // A full or disabled store: the hunt still runs, it just is not remembered.
  }
}

/** The saved hunts for one subject, most recently saved first. */
export function savedHunts(subject: string): SavedHunt[] {
  return read<SavedHunt>(SAVED_KEY, subject).filter(
    (entry) => typeof entry?.name === 'string' && typeof entry?.text === 'string',
  );
}

/**
 * Save a hunt under a name, replacing one with the same name.
 *
 * Replacing rather than refusing: the common case is refining a hunt and keeping the
 * name, and an error dialog for that would train an analyst to use new names — which
 * is how a list of fifty near-identical queries happens.
 */
export function saveHunt(subject: string, name: string, text: string, at: Date): SavedHunt[] {
  const trimmed = name.trim();
  if (trimmed === '' || text.trim() === '') return savedHunts(subject);
  const entry: SavedHunt = { name: trimmed, text: text.trim(), savedAt: at.toISOString() };
  const rest = savedHunts(subject).filter((saved) => saved.name !== trimmed);
  const next = [entry, ...rest].slice(0, SAVED_LIMIT);
  write(SAVED_KEY, subject, next);
  return next;
}

/** Forget one saved hunt by name. */
export function removeHunt(subject: string, name: string): SavedHunt[] {
  const next = savedHunts(subject).filter((saved) => saved.name !== name);
  write(SAVED_KEY, subject, next);
  return next;
}

/** One recently run hunt. */
export interface RecentHunt {
  text: string;
  at: string;
}

/** The recent hunts, newest first. */
export function recentHunts(subject: string): RecentHunt[] {
  return read<RecentHunt>(RECENT_KEY, subject).filter((entry) => typeof entry?.text === 'string');
}

/** Record a hunt that actually ran: deduplicated by text, newest first, capped. */
export function rememberHunt(subject: string, text: string, at: Date): RecentHunt[] {
  const trimmed = text.trim();
  if (trimmed === '') return recentHunts(subject);
  const rest = recentHunts(subject).filter((entry) => entry.text !== trimmed);
  const next = [{ text: trimmed, at: at.toISOString() }, ...rest].slice(0, RECENT_LIMIT);
  write(RECENT_KEY, subject, next);
  return next;
}

/** Forget every recent hunt. */
export function clearRecentHunts(subject: string): void {
  write(RECENT_KEY, subject, []);
}
