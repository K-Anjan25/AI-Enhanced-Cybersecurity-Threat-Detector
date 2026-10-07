/**
 * The connectors panel's derived model (T-422, FR-21).
 *
 * T-422's acceptance criterion has two halves and both are shapes this module owns,
 * so neither is left to a component:
 *
 *   * **Issuing an endpoint shows its signing secret exactly once.** `IssuedSecret`'s
 *     lifetime is the mechanism (`secrets.ts`), and `connectorRows` builds the table
 *     from `WebhookTarget`, whose type has no secret field — so there is no code path
 *     that could put one in the listing. `SECRET_ONCE_NOTE` is the sentence under the
 *     field, and it says the thing a copy-to-clipboard field invites people to get
 *     wrong: the API stores the secret sealed and has no route that returns it, so an
 *     endpoint whose secret is lost is re-issued rather than re-read.
 *   * **A delivery attempt's outcome is readable.** A record carries its target by
 *     *id* (R-58: the list is read across the deployment, a URL names internal
 *     infrastructure), so `deliveryRows` joins the record to the configuration the
 *     same operator is reading. An endpoint that has since been deleted leaves the
 *     record saying so rather than rendering a blank endpoint column — the same
 *     decision the triage queue makes about a missing partition key (T-404).
 *
 * Two more things a screen of this kind gets wrong, and are decided here:
 *
 *   * **The floor is checked, and the URL is not.** `creationReadiness` refuses an
 *     empty URL, a non-https scheme and a length past the API's own limit. It
 *     deliberately does *not* imitate R-55's address rules: the server validates the
 *     allowlist and the resolved address on submit *and* again on every attempt, and a
 *     second copy in the browser would be a rule that drifts and a response that looks
 *     like a client bug. What the client can say, it says; the rest is the server's
 *     refusal, rendered as the server worded it.
 *   * **The delivery window's limits are the server's sentences.** `caveatText` passes
 *     `caveats` through unaltered (as the traffic and log screens do), and
 *     `deliverySummary` reads `dispatch_configured` — the flag that separates "nothing
 *     has been attempted" from "nothing can be attempted in this deployment".
 */
import { formatAge, formatStamp } from '../../lib/format';
import { SEVERITIES } from '../../components/ui';
import type {
  DeliveryList,
  DeliveryRecord,
  WebhookIssued,
  WebhookTarget,
} from '../../api/webhooks';
import type { IssuedSecret } from './secrets';

/** The sentence the panel shows under a freshly issued signing secret. */
export const SECRET_ONCE_NOTE =
  'This is the only time this signing secret is shown. The API stores it sealed and has no route that returns it, so an endpoint whose secret is lost is re-issued rather than re-read.';

/** The most a URL may be, from the API's own schema (2048, `WebhookCreate`). */
export const MAX_URL_LENGTH = 2048;

/** A signing secret, with the lifetime it was given: the dialog that received it. */
export interface IssuedConnector extends IssuedSecret {
  id: string;
  url: string;
  description: string | null;
  severityFloor: string;
  createdAt: string;
}

/** Capture a create response, stamping it with the rendering that may show it. */
export function issuedConnector(issued: WebhookIssued, expiresWith: number): IssuedConnector {
  return {
    id: issued.id,
    url: issued.url,
    description: issued.description,
    severityFloor: issued.severity_floor,
    createdAt: formatStamp(issued.created_at),
    secret: issued.secret,
    expiresWith,
  };
}

/** One endpoint, as the table draws it. There is no secret in `WebhookTarget`. */
export interface ConnectorRow {
  id: string;
  url: string;
  /** The host alone, for the second line: what an operator recognises at a glance. */
  host: string;
  description: string;
  severityFloor: string;
  severityLabel: string;
  active: boolean;
  createdAt: string;
}

/** The host of a URL, or the URL itself when it cannot be parsed. */
export function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/** Title-case a floor the API returned, so the table does not read `high` beside `High`. */
export function floorLabel(floor: string): string {
  return floor.charAt(0).toUpperCase() + floor.slice(1);
}

/** The listing as rows. There is no secret in `WebhookTarget`, so none can appear here. */
export function connectorRows(targets: readonly WebhookTarget[] | undefined): ConnectorRow[] {
  return (targets ?? []).map((target) => ({
    id: target.id,
    url: target.url,
    host: hostOf(target.url),
    description: target.description ?? '',
    severityFloor: target.severity_floor,
    severityLabel: floorLabel(target.severity_floor),
    active: target.active,
    createdAt: formatStamp(target.created_at),
  }));
}

export interface ConnectorSummary {
  total: number;
  floors: string;
  note: string;
}

/**
 * What the panel says above the endpoint table.
 *
 * An empty list is a fact about the deployment rather than a blank table: no endpoint
 * receives anything, which is worth saying in a screen an operator opens to find out
 * whether alerts are leaving the building.
 */
export function connectorSummary(targets: readonly WebhookTarget[] | undefined): ConnectorSummary {
  const all = targets ?? [];
  const counts = new Map<string, number>();
  for (const target of all) {
    const floor = target.severity_floor;
    counts.set(floor, (counts.get(floor) ?? 0) + 1);
  }
  const floors =
    all.length === 0
      ? ''
      : [...counts.entries()].map(([floor, count]) => `${String(count)} at ${floor}`).join(', ');
  return {
    total: all.length,
    floors,
    note:
      all.length === 0
        ? 'No endpoint is registered, so nothing leaves this deployment. Alerts stay in the console until one is added (FR-21).'
        : `${String(all.length)} registered: ${floors}. Every delivery is one signed POST, retried with backoff while the receiver answers with a retryable status.`,
  };
}

/** The severities a floor may be set to, from the one published scale (§5.3). */
export function floorChoices(): readonly string[] {
  return SEVERITIES;
}

export interface CreationReadiness {
  ready: boolean;
  reason: string | null;
}

/**
 * Whether the form may be submitted.
 *
 * The three checks are the ones the browser can make honestly: presence, the scheme
 * the API requires, and its own length limit. Everything about *which* addresses are
 * acceptable belongs to R-55 and is enforced on the server, on submit and again on
 * every attempt — see this module's header for why it is not copied here.
 */
export function creationReadiness(url: string, known: readonly string[]): CreationReadiness {
  const trimmed = url.trim();
  if (trimmed === '') return { ready: false, reason: 'An endpoint needs a URL to deliver to.' };
  if (trimmed.length > MAX_URL_LENGTH) {
    return { ready: false, reason: `A URL may be at most ${String(MAX_URL_LENGTH)} characters.` };
  }
  if (!trimmed.toLowerCase().startsWith('https://')) {
    return {
      ready: false,
      reason: 'A signing secret is only sent over https: plain http would publish the credential.',
    };
  }
  if (known.includes(trimmed)) {
    return {
      ready: false,
      reason: 'That URL is already registered. A duplicate would deliver every alert twice.',
    };
  }
  return { ready: true, reason: null };
}

/** One delivery attempt, with the endpoint it was made to. */
export interface DeliveryRow {
  deliveryId: string;
  /** How the endpoint is named: its host, or its id when it is no longer configured. */
  endpoint: string;
  /**
   * The join behind `endpoint`, in words.
   *
   * The record carries the target by *id* and the configuration carries it by URL
   * (R-58), so the table states which one the row was matched on rather than leaving a
   * reader to assume the match always succeeds. A missing target says so here.
   */
  endpointDetail: string;
  target: string;
  delivered: boolean;
  attempts: string;
  waited: string;
  outcome: string;
  outcomeLabel: string;
  /** §5.3's scale, used as *urgency*: neutral when nothing needs looking at. */
  tone: 'critical' | 'high' | 'neutral';
  status: string;
  reason: string;
  at: string;
  age: string;
}

/**
 * How urgent an outcome is, in §5.3's vocabulary.
 *
 * The tone is urgency rather than severity — the colour says what to look at, the word
 * beside it says what happened — and `neutral` is the badge rule's "not on the scale"
 * chip. Nothing is encoded in colour alone (NFR-09): every row prints the outcome.
 */
export function outcomeTone(outcome: string): 'critical' | 'high' | 'neutral' {
  if (outcome === 'delivered') return 'neutral';
  if (outcome === 'blocked') return 'critical';
  return 'high';
}

/** The outcome's own word, spaced for reading: `transport_error` → `Transport error`. */
export function outcomeLabel(outcome: string): string {
  const spaced = outcome.replace(/_/g, ' ');
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * The records as rows, each joined to its endpoint.
 *
 * A record whose target is no longer configured keeps its row and says so by id: the
 * attempts are a record of what left the building, and a deleted endpoint does not
 * un-send them.
 *
 * The row's age is measured against `nowMs`, which the caller passes in rather than
 * this module reading the clock: a test that wants to know a three-minute-old attempt
 * reads as such should not have to wait three minutes.
 */
export function deliveryRows(
  records: readonly DeliveryRecord[] | undefined,
  targets: readonly WebhookTarget[] | undefined,
  nowMs: number = Date.now(),
): DeliveryRow[] {
  const byId = new Map((targets ?? []).map((target) => [target.id, target]));
  return (records ?? []).map((record) => {
    const target = byId.get(record.target_id);
    return {
      deliveryId: record.delivery_id,
      // The full URL is not repeated here: the configuration table above already names
      // it, and a cell holding the host and then the URL that starts with it is one
      // fact told twice.
      endpoint: target === undefined ? record.target_id : hostOf(target.url),
      endpointDetail: target === undefined ? 'no longer configured' : `target ${record.target_id}`,
      target: record.target_id,
      delivered: record.delivered,
      attempts:
        record.attempt_count === 1 ? '1 attempt' : `${String(record.attempt_count)} attempts`,
      waited: `${record.waited_seconds.toFixed(1)}s backoff`,
      outcome: record.outcome,
      outcomeLabel: outcomeLabel(record.outcome),
      tone: outcomeTone(record.outcome),
      status: record.status === null ? '—' : String(record.status),
      reason: record.reason,
      at: formatStamp(record.at),
      // The age is computed against a clock the caller passes in, so a test can pin
      // it: `formatAge` takes seconds, and a screen that rendered "just now" for every
      // row would hide the one fact this column exists for.
      age: formatAge(Math.max(0, (nowMs - Date.parse(record.at)) / 1_000)),
    };
  });
}

export interface DeliverySummary {
  /** What the table holds, and what the deployment holds behind it. */
  note: string;
  /** Whether this deployment can deliver at all. */
  dispatchConfigured: boolean;
}

/**
 * What the delivery table says above itself.
 *
 * `held` versus `recorded` is the difference between the window and the history: a
 * capped list that said "50 deliveries" would read as the whole story.
 */
export function deliverySummary(list: DeliveryList | undefined): DeliverySummary {
  if (list === undefined) return { note: '', dispatchConfigured: true };
  if (!list.dispatch_configured) {
    return {
      dispatchConfigured: false,
      note: 'Nothing can be sent from this deployment: it has no outbound transport, so this table stays empty. The configuration above is still what a deployment with a transport would deliver to.',
    };
  }
  if (list.items.length === 0) {
    return {
      dispatchConfigured: true,
      note:
        list.recorded === 0
          ? 'Nothing has been delivered yet. An alert at or above an endpoint’s floor is sent as a signed POST, and a test send appears here too.'
          : 'No attempt is held, though this deployment has made some: the window is the newest attempts, and these have aged out.',
    };
  }
  const shown = list.items.length;
  const delivered = list.items.filter((item) => item.delivered).length;
  const capped =
    list.recorded > shown
      ? ` Showing the newest ${String(shown)} of ${String(list.recorded)} attempted.`
      : ` All ${String(shown)} attempted are shown.`;
  return {
    dispatchConfigured: true,
    note: `${String(delivered)} of ${String(shown)} delivered.${capped}`,
  };
}

/** The server's own caveats, as written. Never paraphrased (R-70). */
export function caveatText(list: DeliveryList | undefined): readonly string[] {
  return list?.caveats ?? [];
}
