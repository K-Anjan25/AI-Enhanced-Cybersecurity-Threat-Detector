/**
 * The one-time rule for a secret the API issues (FR-44, FR-21; T-313, T-422).
 *
 * Two credentials exist in this deployment and both are shown exactly once: the API
 * key a collector authenticates with, and the signing secret an outbound endpoint is
 * configured with. The rule has one shape — *a secret is captured with the rendering
 * that received it, and is reachable only while that rendering is the current one* —
 * so it is implemented once, here, and both panels use it. A second copy is how the
 * two credentials would drift apart, and the copy that rots is the one nobody looks
 * at until a secret is on a screen it should have left.
 *
 * The mechanism is a lifetime rather than a flag:
 *
 *   * A capture stamps the value of the panel's open-counter *at the moment the
 *     response arrived* (`expiresWith`).
 *   * `secretIsLive` compares that stamp against the counter *now*, and a panel
 *     passes `null` while its dialog is closed.
 *   * The counter is bumped on the *open* edge, so a dialog opened again cannot show
 *     a capture from a previous rendering. There is no `setSecret(null)` to forget,
 *     and one mechanism rather than two.
 *
 * `secrets.test.ts` asserts the negative case — the same capture against a later
 * rendering is not live — because that is the failure a screenshot never shows: a
 * dialog that looks identical whether its field holds a live secret or nothing.
 */

/** A secret, plus the rendering that is permitted to draw it. */
export interface IssuedSecret {
  readonly secret: string;
  /**
   * The value of the panel's open-counter when the response carrying this secret
   * arrived. A secret is live only while this is that counter's current value.
   */
  readonly expiresWith: number;
}

/**
 * Whether a captured secret may still be rendered.
 *
 * `null` for either argument is a "no": a closed dialog passes `null` for the open
 * token, so the secret becomes unreachable by construction rather than by a caller
 * remembering to clear a field.
 */
export function secretIsLive(issued: IssuedSecret | null, openToken: number | null): boolean {
  return issued !== null && openToken !== null && issued.expiresWith === openToken;
}
