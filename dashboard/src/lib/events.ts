/**
 * NOCTRA Event Bus — a deliberate analog of WordPress hooks.
 *
 * WordPress lets any plugin attach behavior to named points with priority
 * (`add_action('name', cb, priority)`). Our React app gets the same discipline:
 * components dispatch namespaced events (`noctra:open-pending-drawer`) and
 * listeners attach with priority order — no prop drilling, no global state for
 * one-shot UI coordination.
 *
 * - `emit`  = `do_action`      (fire and forget)
 * - `filter` = `apply_filters` (pass a value through ordered transforms)
 * - `on`    = `add_action` / `add_filter` (returns an unsubscribe)
 */

type Listener = (...args: unknown[]) => void;
type FilterFn<T> = (value: T, ...args: unknown[]) => T;

const actions = new Map<string, Map<number, Set<Listener>>>();
const filters = new Map<string, Map<number, Set<FilterFn<unknown>>>>();

export function on(event: string, callback: Listener, priority = 10): () => void {
  if (!actions.has(event)) actions.set(event, new Map());
  const byPriority = actions.get(event)!;
  if (!byPriority.has(priority)) byPriority.set(priority, new Set());
  byPriority.get(priority)!.add(callback);
  return () => off(event, callback, priority);
}

export function off(event: string, callback: Listener, priority = 10): void {
  const byPriority = actions.get(event);
  byPriority?.get(priority)?.delete(callback);
}

export function emit(event: string, ...args: unknown[]): void {
  const byPriority = actions.get(event);
  if (!byPriority) return;
  const priorities = [...byPriority.keys()].sort((a, b) => a - b);
  for (const p of priorities) {
    for (const cb of byPriority.get(p) ?? []) cb(...args);
  }
}

export function addFilter<T>(
  event: string,
  callback: FilterFn<T>,
  priority = 10
): () => void {
  if (!filters.has(event)) filters.set(event, new Map());
  const byPriority = filters.get(event)!;
  if (!byPriority.has(priority)) byPriority.set(priority, new Set());
  byPriority.get(priority)!.add(callback as FilterFn<unknown>);
  return () => removeFilter(event, callback, priority);
}

export function removeFilter<T>(event: string, callback: FilterFn<T>, priority = 10): void {
  const byPriority = filters.get(event);
  byPriority?.get(priority)?.delete(callback as FilterFn<unknown>);
}

export function applyFilters<T>(event: string, value: T, ...args: unknown[]): T {
  const byPriority = filters.get(event);
  if (!byPriority) return value;
  const priorities = [...byPriority.keys()].sort((a, b) => a - b);
  let result: T = value;
  for (const p of priorities) {
    for (const fn of byPriority.get(p) ?? []) {
      result = fn(result, ...args) as T;
    }
  }
  return result;
}

/** Namespaced, documented event names (single registry, WP-hook style). */
export const EVENTS = {
  COMMAND_MENU: "noctra:command-menu", // ⌘K — open command palette
  OPEN_PENDING_DRAWER: "noctra:open-pending-drawer", // mini-cart pattern: show pending decisions
  CLOSE_PENDING_DRAWER: "noctra:close-pending-drawer",
  PENDING_CHANGED: "noctra:pending-changed", // payload: number — live count refresh
  TOAST: "noctra:toast", // payload: { message, tone? }
} as const;

export type NoctraEvent = (typeof EVENTS)[keyof typeof EVENTS];

export default { EVENTS, on, off, emit, addFilter, removeFilter, applyFilters };
