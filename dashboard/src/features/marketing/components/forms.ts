import { postVoid } from '../../../api/client';

/**
 * Shared form rules for the newsletter and contact forms.
 *
 * Each form posts to a server-relative path, read from a Vite env var, through the typed
 * client in `src/api/` (rule R-23). In production nginx proxies `/api/` to the back end,
 * so the path needs no origin. When a path is empty, the form says so and sends nothing:
 * a visitor is never told a message was delivered when it was not.
 */

export const NEWSLETTER_PATH: string = import.meta.env.VITE_NEWSLETTER_PATH ?? '';
export const CONTACT_PATH: string = import.meta.env.VITE_CONTACT_PATH ?? '';

/** Deliberately simple: the server validates properly; this only catches typos early. */
export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function isEmail(value: string): boolean {
  return EMAIL_PATTERN.test(value.trim());
}

export type FormStatus =
  | { state: 'idle'; message: '' }
  | { state: 'loading'; message: string }
  | { state: 'success'; message: string }
  | { state: 'error'; message: string };

export const IDLE: FormStatus = { state: 'idle', message: '' };

/** Sends a form body. Resolves when the server accepts it, and throws otherwise. */
export async function submitForm(path: string, body: unknown): Promise<void> {
  await postVoid(path, body);
}
