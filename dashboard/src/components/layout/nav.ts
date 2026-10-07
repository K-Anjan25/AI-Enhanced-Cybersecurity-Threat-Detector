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
 *
 * **The icon is part of the destination, and it is required.** design.md §5.6 makes
 * the icon set Lucide, and §3's rail "collapses to a 56 px icon rail" — which means
 * every entry needs a drawn icon before it can be shown collapsed at all. The rail
 * that shipped before this had none, so the collapsed rail rendered each label's
 * first letter (`O`, `A`, `T`, …): a 56 px column of letters is not an icon rail,
 * and two sections whose labels share a letter are indistinguishable in it. The
 * icon lives here rather than in `AppShell` because the rail is not the only place
 * a destination is drawn — admin's section nav draws the same six destinations —
 * and an icon chosen at the render site is how one screen gets a symbol and the
 * other does not.
 */
import {
  Crosshair,
  Cpu,
  Database,
  FileClock,
  KeyRound,
  LayoutDashboard,
  Network,
  Plug,
  ScrollText,
  Settings,
  ShieldAlert,
  SlidersHorizontal,
  TrendingDown,
  Users,
  type LucideIcon,
} from 'lucide-react';

/** A destination nested under an area whose page has a section nav of its own. */
export interface NavLeaf {
  /** The path relative to the area's route, which is what a nested `Routes` needs. */
  readonly path: string;
  /** The absolute href, which is what the rail, the index and the palette need. */
  readonly to: string;
  readonly label: string;
  /**
   * The Lucide icon for this destination (design.md §5.6), required on every entry.
   *
   * A component rather than a name, so the icon set is checked at compile time and
   * a render site cannot reach for a glyph of its own.
   */
  readonly icon: LucideIcon;
  /** Words an operator may search for that the label does not contain. */
  readonly keywords?: readonly string[];
}

export interface NavItem {
  /** The route. */
  readonly to: string;
  readonly label: string;
  /** The Lucide icon for this destination (design.md §5.6). */
  readonly icon: LucideIcon;
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
  {
    path: 'users',
    to: '/admin/users',
    label: 'Users & roles',
    icon: Users,
    keywords: ['roles', 'people'],
  },
  {
    path: 'keys',
    to: '/admin/keys',
    label: 'API keys',
    icon: KeyRound,
    keywords: ['token', 'credential'],
  },
  {
    path: 'connectors',
    to: '/admin/connectors',
    label: 'Connectors',
    icon: Plug,
    keywords: ['webhook', 'endpoint', 'signing', 'delivery', 'hmac'],
  },
  {
    path: 'thresholds',
    to: '/admin/thresholds',
    label: 'Thresholds',
    icon: SlidersHorizontal,
    keywords: ['bands', 'scores'],
  },
  {
    path: 'retention',
    to: '/admin/retention',
    label: 'Retention & GDPR',
    icon: Database,
    keywords: ['erasure'],
  },
  {
    path: 'audit',
    to: '/admin/audit',
    label: 'Audit log',
    icon: FileClock,
    keywords: ['history', 'ledger'],
  },
];

/**
 * The rail's entries, in the order design.md §3 lists them.
 *
 * Each icon is the design's own vocabulary for the screen, not a decoration: the
 * overview is a dashboard, traffic is a network, the audit log is a clock over a
 * file. `Logs` and `Audit log` are the pair a first draft gets wrong — both are
 * document-shaped, and two entries drawn with the same symbol in one rail read as
 * one thing rendered twice, so the log stream is a scroll and the audit log is a
 * file with a clock.
 */
export const NAV_ITEMS: readonly NavItem[] = [
  {
    to: '/',
    label: 'Overview',
    icon: LayoutDashboard,
    section: 'Monitor',
    keywords: ['dashboard', 'kpi'],
  },
  {
    to: '/alerts',
    label: 'Alerts',
    icon: ShieldAlert,
    section: 'Threats',
    keywords: ['triage', 'queue', 'verdict'],
  },
  {
    to: '/traffic',
    label: 'Traffic',
    icon: Network,
    section: 'Explore',
    keywords: ['flows', 'entities'],
  },
  {
    to: '/logs',
    label: 'Logs',
    icon: ScrollText,
    section: 'Explore',
    keywords: ['tail', 'clusters', 'events'],
  },
  {
    to: '/hunt',
    label: 'Hunt',
    icon: Crosshair,
    section: 'Explore',
    keywords: ['query', 'search', 'saved'],
  },
  {
    to: '/models',
    label: 'Model ops',
    icon: Cpu,
    section: 'Models',
    keywords: ['registry', 'promote', 'rollback', 'version'],
  },
  {
    to: '/models/drift',
    label: 'Drift',
    icon: TrendingDown,
    section: 'Models',
    keywords: ['psi', 'shift', 'decay'],
  },
  {
    to: '/admin',
    label: 'Admin',
    icon: Settings,
    section: 'Admin',
    keywords: ['settings', 'governance'],
    // One rail entry, because the design's Admin sub-tree is the page's own section
    // nav (see the note in AppShell). The palette lists the children anyway: jumping
    // straight to the audit log is the whole point of a command palette.
    children: ADMIN_SECTIONS,
  },
];

/** A palette destination: what `navDestinations` offers, and all it needs. */
export interface NavDestination {
  readonly to: string;
  readonly label: string;
  readonly keywords?: readonly string[];
}

/**
 * Every destination the palette can navigate to: the rail's areas, then their
 * children. Flattened here rather than in the palette so the order is one decision,
 * and so a test can assert the two lists agree.
 *
 * The palette's rows are a filtered list rather than a rail: the operator has typed
 * the screen's name by the time a row is on screen, so an icon there would be a
 * second, unpriced way to misspell the same set. The icons stay on the destinations
 * they belong to; this function is deliberately narrower than the model.
 */
export function navDestinations(): readonly NavDestination[] {
  const destinations: NavDestination[] = [];
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
