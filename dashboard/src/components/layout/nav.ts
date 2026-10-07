/**
 * The information architecture (design.md §3), as data.
 *
 * This was `AppShell`'s private constant until T-411 needed it in a second place:
 * the command palette navigates, so it needs the same list the rail renders. A
 * second copy of the routes is how the palette learns to offer a screen the rail
 * does not have — or, worse, how a renamed route keeps working in one of them — so
 * the list moved to one module that both read.
 *
 * It sits in `components` rather than `lib` because it is the shell's own model: the
 * palette (a feature) may import down into it, and the shell may import its own
 * layer. `lib` is for things that are true of any app; this is this app's IA.
 */

/** A destination nested under an area whose page has a section nav of its own. */
export interface NavLeaf {
  /** The path relative to the area's route, which is what a nested `Routes` needs. */
  readonly path: string;
  /** The absolute href, which is what the rail, the index and the palette need. */
  readonly to: string;
  readonly label: string;
  /** Words an operator may search for that the label does not contain. */
  readonly keywords?: readonly string[];
}

export interface NavItem {
  /** The route. */
  readonly to: string;
  readonly label: string;
  /** The rail's grouping, which the palette also uses to order destinations. */
  readonly section: string;
  /**
   * Words an operator may search for that the label does not contain.
   *
   * The palette is searched by what a screen is *called* at the desk: `keys` for
   * API keys, `history` for the audit log, `psi` for drift.
   */
  readonly keywords?: readonly string[];
  /** Destinations under this area, when the area has a section nav of its own. */
  readonly children?: readonly NavLeaf[];
}

/** The relative path of one admin section, as a union, so the page's map is total. */
export type AdminSectionPath =
  'users' | 'keys' | 'connectors' | 'thresholds' | 'retention' | 'audit';

/** An admin section: a nav destination whose `path` is a known relative route. */
export interface AdminNavLeaf extends NavLeaf {
  readonly path: AdminSectionPath;
}

/**
 * Admin's sections, which the page renders as its own nav and the palette lists as
 * destinations.
 *
 * All six of design.md §3's children are here now. `connectors` was absent until T-422
 * built the screen — a palette entry for a screen that did not exist would have been a
 * command that navigated to an apology — and it is listed in the design's own order,
 * between the credentials and the thresholds.
 *
 * Declared before `NAV_ITEMS`, which embeds it: a `const` is not readable above its
 * own initialisation.
 */
export const ADMIN_SECTIONS: readonly AdminNavLeaf[] = [
  { path: 'users', to: '/admin/users', label: 'Users & roles', keywords: ['roles', 'people'] },
  { path: 'keys', to: '/admin/keys', label: 'API keys', keywords: ['token', 'credential'] },
  {
    path: 'connectors',
    to: '/admin/connectors',
    label: 'Connectors',
    keywords: ['webhook', 'endpoint', 'signing', 'delivery', 'hmac'],
  },
  {
    path: 'thresholds',
    to: '/admin/thresholds',
    label: 'Thresholds',
    keywords: ['bands', 'scores'],
  },
  { path: 'retention', to: '/admin/retention', label: 'Retention & GDPR', keywords: ['erasure'] },
  { path: 'audit', to: '/admin/audit', label: 'Audit log', keywords: ['history', 'ledger'] },
];

/** The rail's entries, in the order design.md §3 lists them. */
export const NAV_ITEMS: readonly NavItem[] = [
  { to: '/', label: 'Overview', section: 'Monitor', keywords: ['dashboard', 'kpi'] },
  { to: '/alerts', label: 'Alerts', section: 'Threats', keywords: ['triage', 'queue', 'verdict'] },
  { to: '/traffic', label: 'Traffic', section: 'Explore', keywords: ['flows', 'entities'] },
  { to: '/logs', label: 'Logs', section: 'Explore', keywords: ['tail', 'clusters', 'events'] },
  { to: '/hunt', label: 'Hunt', section: 'Explore', keywords: ['query', 'search', 'saved'] },
  {
    to: '/models',
    label: 'Model ops',
    section: 'Models',
    keywords: ['registry', 'promote', 'rollback', 'version'],
  },
  { to: '/models/drift', label: 'Drift', section: 'Models', keywords: ['psi', 'shift', 'decay'] },
  {
    to: '/admin',
    label: 'Admin',
    section: 'Admin',
    keywords: ['settings', 'governance'],
    // One rail entry, because the design's Admin sub-tree is the page's own section
    // nav (see the note in AppShell). The palette lists the children anyway: jumping
    // straight to the audit log is the whole point of a command palette.
    children: ADMIN_SECTIONS,
  },
];

/**
 * Every destination the palette can navigate to: the rail's areas, then their
 * children. Flattened here rather than in the palette so the order is one decision,
 * and so a test can assert the two lists agree.
 */
export function navDestinations(): readonly Omit<NavLeaf, 'path'>[] {
  const destinations: Omit<NavLeaf, 'path'>[] = [];
  for (const item of NAV_ITEMS) {
    destinations.push({
      to: item.to,
      label: item.label,
      ...(item.keywords === undefined ? {} : { keywords: item.keywords }),
    });
    for (const child of item.children ?? []) destinations.push(child);
  }
  return destinations;
}
