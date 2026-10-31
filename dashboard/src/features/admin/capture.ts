/**
 * The capture panel's rules (step 4).
 *
 * The panel is a control for a desired state, so the rules are about what the operator
 * may ask for, and what the screen may claim while the sensor catches up:
 *
 *   * **Starting needs at least one engine.** The API refuses it too; the panel does
 *     not offer the request.
 *   * **The engine list keeps its catalogue order.** A set of checkboxes that reorders
 *     itself on every click reads as a bug.
 *   * **The panel never says capture is running on the sensor.** It says what was asked
 *     for and when. The sensor applies it within a few seconds, and it may not be up.
 */
import type { CaptureState } from '../../api/capture';

export const CAPTURE_ENGINES = [
  {
    id: 'suricata',
    label: 'Suricata',
    note: 'Flows, alerts, DNS, HTTP and TLS. No rules are loaded yet.',
  },
  {
    id: 'tshark',
    label: 'tshark',
    note: 'Packet-level flows. Duplicates Suricata’s flows, so it is off unless chosen.',
  },
] as const;

export type CaptureEngine = (typeof CAPTURE_ENGINES)[number]['id'];

const KNOWN: ReadonlySet<string> = new Set(CAPTURE_ENGINES.map((engine) => engine.id));

/** Keep only known engines, in catalogue order. */
export function orderEngines(engines: readonly string[]): CaptureEngine[] {
  return CAPTURE_ENGINES.map((engine) => engine.id).filter((id) => engines.includes(id));
}

/** Toggle one engine, keeping the catalogue order and dropping anything unknown. */
export function toggleEngine(selected: readonly string[], engine: string): CaptureEngine[] {
  if (!KNOWN.has(engine)) return orderEngines(selected);
  const next = selected.includes(engine)
    ? selected.filter((id) => id !== engine)
    : [...selected, engine];
  return orderEngines(next);
}

/** Starting needs at least one engine. Stopping never does. */
export function canStart(selected: readonly string[]): boolean {
  return orderEngines(selected).length > 0;
}

/** What the panel says the desired state is. It never claims the sensor has applied it. */
export function describeRequest(state: Pick<CaptureState, 'running' | 'engines'>): string {
  if (!state.running) {
    return 'Capture is stopped. The sensor stops its engines within a few seconds.';
  }
  return `Capture is requested on ${orderEngines(state.engines).join(', ') || 'no engines'}. The sensor starts them within a few seconds.`;
}

/** The sentence under the controls, which states the boundary of this panel. */
export const CAPTURE_SCOPE_NOTE =
  'This sets what the capture sensor should run. It does not start or stop the container, and a restart of the capture container comes back stopped.';
