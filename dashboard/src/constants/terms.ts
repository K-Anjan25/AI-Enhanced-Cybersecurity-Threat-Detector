/**
 * NOCTRA Terminology — "plain English first, formal technical always available."
 *
 * The analyst pain point this solves: security jargon (blast radius, MITRE,
 * SOAR, action_type) assumes a trained SOC analyst. NOCTRA's analysts are
 * often founders, IT generalists or engineers — so every technical term in
 * the UI is dogfooded through this dictionary: the *display* stays formal and
 * precise, but a plain-English gloss is one hover/focus away, and the first
 * occurrence on a screen can render the plain gloss inline.
 *
 * Convention: `plain` = what a colleague would say; `formal` = the exact
 * technical definition (used in reports/audit). Never hand-wave — if a term
 * isn't here, add it; the audit table lives in
 * docs/terminology-playbook.md.
 */

export interface TermEntry {
  /** One-sentence plain-English gloss (the default tooltip body). */
  plain: string;
  /** Formal technical definition, shown under "Technical:" in the tooltip. */
  formal: string;
}

export const TERMS = {
  "blast radius": {
    plain: "What's affected — every account, host, IP and file connected to this incident.",
    formal:
      "Entity graph reachable from the case's root entity (accounts, hosts, IPs, domains, files linked by observed relations).",
  },
  confidence: {
    plain: "How sure NOCTRA is, based on the evidence it actually has.",
    formal: "Normalized model/heuristic probability (0–100%) assigned by the detection pipeline.",
  },
  mitre: {
    plain: "A shared industry catalog of attacker techniques, so everyone names the same behavior the same way.",
    formal: "MITRE ATT&CK knowledge base of adversary tactics and techniques.",
  },
  T1078: {
    plain: "Valid Accounts — the attacker signed in with a real credential instead of breaking in.",
    formal: "MITRE ATT&CK technique T1078: Valid Accounts (use of legitimate credentials to access systems).",
  },
  T1566: {
    plain: "Phishing — an email designed to trick someone into clicking or sharing a secret.",
    formal: "MITRE ATT&CK technique T1566: Phishing.",
  },
  T1048: {
    plain: "Exfiltration — data moving out of your network to an attacker-controlled place.",
    formal: "MITRE ATT&CK technique T1048: Exfiltration Over Alternative Protocol.",
  },
  T1098: {
    plain: "Account manipulation — the attacker changed account settings to keep access.",
    formal: "MITRE ATT&CK technique T1098: Account Manipulation.",
  },
  SOAR: {
    plain: "Automation that turns rules into recorded actions for repeatable situations.",
    formal: "Security Orchestration, Automation and Response — the engine that evaluates rules and records actions.",
  },
  playbook: {
    plain: "A saved, repeatable sequence of automated steps for a known situation.",
    formal: "Reusable SOAR workflow definition (trigger → conditions → recorded actions).",
  },
  "record-only": {
    plain: "NOCTRA writes the action to the log but never runs it against your systems.",
    formal: "SOAR executed in record-only mode: the action row is persisted; no external side effects are performed.",
  },
  reversible: {
    plain: "The action can be undone, and NOCTRA tells you exactly how.",
    formal: "A compensating control is drafted for the proposed action before approval.",
  },
  "REVOKE_CREDENTIALS": {
    plain: "Revoke this login so the stolen password stops working.",
    formal: "SOAR action type REVOKE_CREDENTIALS: disable/rotate the affected credential and invalidate its sessions.",
  },
  connector: {
    plain: "A live link to one of your tools — Okta, CrowdStrike, GuardDuty or Cloudflare.",
    formal: "Ingestion connector: authenticated source with sync status, latency and asset count.",
  },
  telemetry: {
    plain: "The raw signals your tools send NOCTRA.",
    formal: "Structured event stream produced by connectors and normalized for detection.",
  },
  entity: {
    plain: "A thing NOCTRA tracks — an account, host, IP, domain or file.",
    formal: "Typed node in the entity graph (account/host/ip/domain/email/file/hash).",
  },
  IOC: {
    plain: "A known-bad indicator — a suspicious IP, hash or domain.",
    formal: "Indicator of Compromise: an observable linked to known malicious activity.",
  },
  reputation: {
    plain: "How trustworthy an IP or domain looks, from threat intelligence.",
    formal: "Threat-intel reputation score (blacklist, ASN, age, observed abuse).",
  },
  provenance: {
    plain: "Where a piece of evidence came from.",
    formal: "Source attribution for an evidence record (connector, batch, upload).",
  },
  remediation: {
    plain: "The fix for what went wrong.",
    formal: "Planned corrective action targeting the root cause of the incident.",
  },
  case: {
    plain: "One incident NOCTRA is walking you through, from explanation to decision.",
    formal: "Investigation unit aggregating evidence, analysis, blast radius and decision state.",
  },
  decision: {
    plain: "Your call — approve, decline, or reverse the proposed action.",
    formal: "Human gate in the analyst loop; transitions are persisted and audited.",
  },
  undo: {
    plain: "The exact step to reverse an action after it's recorded.",
    formal: "Compensating action for reversibility, recorded alongside the original action.",
  },
  detection: {
    plain: "A rule or model that flags unusual behavior worth looking at.",
    formal: "Heuristic, ML model or rule evaluation producing a SecurityAlert.",
  },
  "pending decision": {
    plain: "A case waiting for your approve or decline call.",
    formal: "Case in `pending` decision state with a proposed action drafted.",
  },
  "auto-recorded": {
    plain: "Recorded automatically by a rule, without a human step — still reversible and audited.",
    formal: "SOAR action auto-recorded by rule evaluation in record-only mode.",
  },
} as const satisfies Record<string, TermEntry>;

/** Lookup with fuzzy key fallback (case-insensitive, ignores trailing punctuation). */
export function lookupTerm(key: string): TermEntry | undefined {
  if (!key) return undefined;
  const normalized = key.trim().toLowerCase().replace(/[.?!,;:]$/, "");
  return (TERMS as Record<string, TermEntry | undefined>)[normalized];
}

export default TERMS;
