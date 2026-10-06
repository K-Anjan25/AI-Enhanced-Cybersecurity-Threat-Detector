/**
 * The users and roles panel's derived model (T-410, R-53).
 *
 * T-410's first acceptance criterion — *the last `admin` cannot self-demote* — is
 * enforced by the server, and this file's job is to make that enforcement visible
 * rather than to duplicate it:
 *
 *   * **The mark comes from the server's own count.** `active_admins` is the number
 *     the 409 is decided by, so a row is marked "last active admin" when that count
 *     is 1 and the row is an active admin. Counting rows here would be a second
 *     implementation of a rule with one authority, and the two would disagree the
 *     first time a disabled account was involved.
 *   * **The control is offered, and the refusal is explained.** A demotion of the
 *     last admin is refused with the server's sentence (a 409 whose body this client
 *     never parses, so `hooks.ts` maps the status to a sentence of its own *for the
 *     screen* and the server's message is only rendered when the API returns one in
 *     a shape a screen may show — it does not here; see `roleRefusalMessage`).
 *     Hiding the control would teach nothing; the sentence teaches the rule.
 *   * **A no-op is not a change.** `changed: false` means the server wrote nothing
 *     and the trail recorded nothing, and the panel says so instead of reporting a
 *     successful change (D-038's rule, the same one the promotion modal obeys).
 *
 * Roles are ordered viewer → analyst → responder → admin, which is R-53's own
 * ordering and *not* an escalation ladder: the capabilities are declared per role in
 * the server's matrix, and this model never derives one role's powers from another's.
 */
import type { AdminUser, RoleInfo, UserList } from '../../api/admin';

/** R-53's roles, in the order the server lists them. */
export const ROLE_ORDER: readonly string[] = ['viewer', 'analyst', 'responder', 'admin'];

/** How a role renders: a label, not a synonym for its capabilities. */
export const ROLE_LABELS: Readonly<Record<string, string>> = {
  viewer: 'Viewer',
  analyst: 'Analyst',
  responder: 'Responder',
  admin: 'Admin',
};

export interface UserRow {
  id: number;
  email: string;
  role: string;
  roleLabel: string;
  createdAt: string;
  /** When the account stopped being usable, or an empty string when it works. */
  disabledAt: string;
  disabled: boolean;
  /** True for the account the server's count says is the only one left. */
  lastActiveAdmin: boolean;
  /** The sentence explaining why a demotion would be refused, or null. */
  demotionRefusal: string | null;
}

/** The sentence a row carries when it is the deployment's only way in. */
export const LAST_ADMIN_NOTE =
  'The only active admin: changing this role would leave nobody able to administer users, keys, retention or models (R-53).';

/**
 * The directory, with the mark and the refusal sentence on every row.
 *
 * `active_admins` is the server's, and a missing or non-numeric count is treated as
 * "unknown" — no row is marked — rather than as zero, which would mark nothing and
 * read as "the rule does not apply here".
 */
export function userRows(list: UserList | undefined): UserRow[] {
  if (list === undefined) return [];
  const admins = typeof list.active_admins === 'number' ? list.active_admins : null;
  return list.items.map((user: AdminUser): UserRow => {
    const disabled = user.disabled_at !== null;
    const lastActiveAdmin = admins === 1 && user.role === 'admin' && !disabled;
    return {
      id: user.id,
      email: user.email,
      role: user.role,
      roleLabel: ROLE_LABELS[user.role] ?? user.role,
      createdAt: user.created_at,
      disabledAt: user.disabled_at ?? '',
      disabled,
      lastActiveAdmin,
      demotionRefusal: lastActiveAdmin ? LAST_ADMIN_NOTE : null,
    };
  });
}

/** What the panel says about the directory as a whole. */
export interface UserSummary {
  count: number;
  activeAdmins: number;
  /** The sentence under the table, which is the rule stated once. */
  note: string;
  /** True when the deployment cannot administer itself — a fact worth shouting. */
  stranded: boolean;
}

export function userSummary(list: UserList | undefined): UserSummary {
  const count = list?.count ?? 0;
  const activeAdmins = list?.active_admins ?? 0;
  const stranded = count > 0 && activeAdmins === 0;
  return {
    count,
    activeAdmins,
    note: stranded
      ? 'No active admin is registered: nobody can change roles, keys, thresholds, retention or models. This is a deployment state, not a permission you can grant from here.'
      : `${String(activeAdmins)} active ${activeAdmins === 1 ? 'admin' : 'admins'} of ${String(count)} ${count === 1 ? 'account' : 'accounts'}. A change that would leave zero is refused.`,
    stranded,
  };
}

export interface RoleChoice {
  role: string;
  label: string;
  /** What the role may do, from the server's matrix. */
  capabilities: string[];
  /** The wording for one capability, so the choice is explicable in a list. */
  describes: string;
}

/** Capability names as a person reads them. */
export const CAPABILITY_LABELS: Readonly<Record<string, string>> = {
  read: 'read alerts, logs and models',
  verdict: 'record verdicts',
  export: 'export data',
  webhook_config: 'configure webhooks',
  ingest: 'ingest telemetry',
  users: 'manage users and roles',
  models: 'promote models and move thresholds',
  retention: 'run retention and erasure',
  api_keys: 'issue and revoke API keys',
};

/**
 * The four roles with what each may do, read from the server's own listing.
 *
 * The order is R-53's, and a role the server did not describe is appended rather
 * than dropped: a role this build does not know about is a fact about the
 * deployment, not a row to hide.
 */
export function roleChoices(roles: readonly RoleInfo[] | undefined): RoleChoice[] {
  const known = roles ?? [];
  const ordered = [
    ...ROLE_ORDER.map((name) => known.find((info) => info.role === name)).filter(
      (info): info is RoleInfo => info !== undefined,
    ),
    ...known.filter((info) => !ROLE_ORDER.includes(info.role)),
  ];
  return ordered.map((info) => ({
    role: info.role,
    label: ROLE_LABELS[info.role] ?? info.role,
    capabilities: info.capabilities,
    describes: info.capabilities
      .map((capability) => CAPABILITY_LABELS[capability] ?? capability)
      .join(', '),
  }));
}

/**
 * Whether a role change is worth sending.
 *
 * The check is *equality with what the user already holds*, which is the server's
 * own no-op rule stated as a predicate: sending the same role is a request whose
 * only possible outcomes are "nothing happened" and a race with another admin's
 * change. The screen disables the control instead of sending it.
 */
export function roleChangeRequired(current: string, chosen: string | null): boolean {
  return chosen !== null && chosen !== current;
}
