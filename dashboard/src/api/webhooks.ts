/**
 * The webhook configuration and delivery API (FR-21, T-311, T-422).
 *
 * Two properties of this module are rules rather than formatting, and both mirror
 * the server's own shape:
 *
 *   * **`WebhookIssued` is not `WebhookTarget`, and only the create call returns it.**
 *     The signing secret is a field of the creation response and of nothing else, so
 *     the listing — and the delivery list beside it — cannot render one even if a
 *     screen tried to: the type has no such field. It is the same guarantee
 *     `ApiKeyIssued` carries for API keys (T-313's rule, applied to the other
 *     credential this deployment issues).
 *   * **A delivery record carries the target by id, never by URL.** The records are
 *     read across the whole deployment while a target's URL names internal
 *     infrastructure, so the server sends ids and the screen joins them against the
 *     configuration it is already allowed to read (R-53, R-58).
 *
 * `GET /deliveries` answers what this deployment has attempted, plus what qualifies
 * it: `dispatch_configured` is false in a build with no outbound transport, which is
 * what tells an empty table apart from an endpoint nothing has reached, and
 * `caveats` are the server's own sentences about the window's limits. They are
 * rendered as written, never paraphrased — a second copy of a caveat is how one of
 * them stops being true.
 */
import { deleteJson, getJson, postJson, query } from './client';

export const WEBHOOKS_PATH = '/api/v1/webhooks';

/** Where the recent attempts are read. A sibling of the listing, not a child of it. */
export const DELIVERIES_PATH = '/api/v1/webhooks/deliveries';

/**
 * One configured endpoint, as the listing returns it.
 *
 * There is no secret field, by design: the API has no route that returns one again.
 */
export interface WebhookTarget {
  id: string;
  url: string;
  description: string | null;
  /** The lowest severity this endpoint receives: `high` or `critical` by default. */
  severity_floor: string;
  active: boolean;
  created_at: string;
}

/**
 * A newly registered endpoint.
 *
 * The only type in the dashboard that carries a signing secret, and it exists only as
 * the answer to one POST. A lost secret is re-issued rather than re-read: the server
 * stores it sealed and has no route that opens it.
 */
export interface WebhookIssued extends WebhookTarget {
  secret: string;
}

export interface WebhookList {
  items: WebhookTarget[];
}

/** One delivery attempt, as `GET /api/v1/webhooks/deliveries` returns it. */
export interface DeliveryRecord {
  delivery_id: string;
  target_id: string;
  /** When the delivery finished, on the API's clock. */
  at: string;
  delivered: boolean;
  /** Requests made, retries included. */
  attempt_count: number;
  /** Time spent in backoffs between them. */
  waited_seconds: number;
  /** The last attempt: delivered, retry, rejected, blocked or transport_error. */
  outcome: string;
  status: number | null;
  /** A short code, never a message from the receiver. */
  reason: string;
}

export interface DeliveryList {
  items: DeliveryRecord[];
  /** How many records the server still holds, which may exceed what it returned. */
  held: number;
  /** How many it has made in its lifetime, dropped ones included. */
  recorded: number;
  /** Whether this deployment has a sender at all, so an empty list can be read. */
  dispatch_configured: boolean;
  caveats: string[];
}

/** A target to register. The floor is the API's own vocabulary, checked server-side. */
export interface WebhookCreate {
  url: string;
  description?: string | undefined;
  severity_floor: string;
}

/** What the listing asks for by default, and the most it will serve. */
export const DELIVERY_READ_LIMIT = 50;
export const DELIVERY_READ_MAX = 200;

/** `DELETE /api/v1/webhooks/{webhook_id}` — remove an endpoint. */
export function webhookPath(webhookId: string): string {
  return `${WEBHOOKS_PATH}/${encodeURIComponent(webhookId)}`;
}

/** `POST /api/v1/webhooks/{webhook_id}/test` — one attempt, no retries. */
export function webhookTestPath(webhookId: string): string {
  return `${webhookPath(webhookId)}/test`;
}

/** The delivery read, with its window. */
export function deliveriesPath(limit: number = DELIVERY_READ_LIMIT): string {
  return `${DELIVERIES_PATH}${query({ limit })}`;
}

/** Every registered target, never with a secret. */
export async function fetchWebhooks(signal?: AbortSignal): Promise<WebhookList> {
  return getJson<WebhookList>(WEBHOOKS_PATH, { signal });
}

/** Register an endpoint. The response is the one and only place its secret exists. */
export async function createWebhook(body: WebhookCreate): Promise<WebhookIssued> {
  return postJson<WebhookIssued>(WEBHOOKS_PATH, body);
}

/** Remove an endpoint. Deliveries already attempted keep their record. */
export async function deleteWebhook(webhookId: string): Promise<void> {
  await deleteJson(webhookPath(webhookId));
}

/** The attempts this deployment has made, newest first, with what qualifies them. */
export async function fetchDeliveries(
  limit: number = DELIVERY_READ_LIMIT,
  signal?: AbortSignal,
): Promise<DeliveryList> {
  return getJson<DeliveryList>(deliveriesPath(limit), { signal });
}

/** Attempt one delivery to a target and return what happened. */
export async function testWebhook(webhookId: string): Promise<DeliveryRecord> {
  return postJson<DeliveryRecord>(webhookTestPath(webhookId), {});
}
