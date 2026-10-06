/**
 * A viewport, for tests (T-412).
 *
 * jsdom has no `matchMedia`, so a component that lays itself out for a narrow window
 * has nothing to read and silently takes the wide path. This installs one that
 * answers design.md §8.3's queries for a width the test chooses — and answers them
 * the way a browser would, by comparing the width to the bound the query names rather
 * than by returning a canned class. That is what keeps the tests honest: they exercise
 * the real query strings from `lib/viewport.ts`, so a query that asked for the wrong
 * boundary would fail a test here rather than pass one.
 *
 * `setWidth` dispatches `change` to the listeners whose answer flipped, exactly as a
 * browser does on a resize, so the re-render path is tested rather than assumed.
 *
 * It is installed with `vi.stubGlobal`, so `vi.unstubAllGlobals()` in an `afterEach`
 * removes it and no other test inherits a width.
 */
import { vi } from 'vitest';

/** The bound a `(max-width: …)` query names, which is the only shape §8.3 uses. */
const MAX_WIDTH = /\(max-width:\s*([\d.]+)px\)/;

interface RegisteredList {
  readonly query: string;
  matches: boolean;
  readonly listeners: Set<() => void>;
}

export interface ViewportStub {
  /** The width the stub is currently answering for. */
  readonly width: number;
  /** Resize the window, notifying every listener whose query flipped. */
  setWidth(width: number): void;
}

/**
 * Install a `matchMedia` that answers for `width`, defaulting to §8.3's full layout.
 *
 * A query the stub does not understand — `prefers-color-scheme`, say, which the theme
 * provider asks — answers `false`, which is what jsdom-without-matchMedia amounts to
 * for a `prefers-*` question.
 */
export function stubViewport(width = 1440): ViewportStub {
  const lists = new Set<RegisteredList>();
  let current = width;

  const answer = (query: string): boolean => {
    const bound = MAX_WIDTH.exec(query);
    if (bound === null) return false;
    return current <= Number.parseFloat(bound[1]!);
  };

  vi.stubGlobal('matchMedia', (query: string) => {
    const list: RegisteredList = { query, matches: answer(query), listeners: new Set() };
    lists.add(list);
    return {
      media: query,
      get matches() {
        return list.matches;
      },
      addEventListener: (type: string, listener: () => void) => {
        if (type === 'change') list.listeners.add(listener);
      },
      removeEventListener: (type: string, listener: () => void) => {
        if (type === 'change') list.listeners.delete(listener);
      },
    } as unknown as MediaQueryList;
  });

  return {
    get width() {
      return current;
    },
    setWidth(next: number) {
      current = next;
      for (const list of lists) {
        const matches = answer(list.query);
        if (matches === list.matches) continue;
        list.matches = matches;
        for (const listener of list.listeners) listener();
      }
    },
  };
}
