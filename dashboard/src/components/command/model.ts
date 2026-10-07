/**
 * The command model (design.md §5.5: `CommandPalette` — "`⌘K`; navigates, filters,
 * and runs saved hunts").
 *
 * A command is data, not a component: an id, the words that identify it, and a
 * `run` callback. That is what makes the palette's two behaviours testable without
 * a DOM — *filtering* is a pure function of the list and the query, and *selection*
 * is a pure function of the index and the arrow key — and it is what lets the same
 * list be rendered by the palette and asserted on by a screen's own tests.
 *
 * The model lives beside the palette rather than in the feature that wires it,
 * because the palette is a §6 component: it must be renderable from props alone,
 * with no knowledge of which routes this build has or where a saved hunt is kept.
 */

/** The three sections of the palette, in the order they are shown. */
export type CommandGroup = 'Navigation' | 'Saved hunts' | 'Actions';

export interface Command {
  /** Stable identity, `group:slug`. Used for `aria-activedescendant` and tests. */
  readonly id: string;
  readonly label: string;
  /** The line under the label: a path, the query, or what the action does. */
  readonly hint?: string | undefined;
  readonly group: CommandGroup;
  /**
   * Extra words this command answers to.
   *
   * A command palette is searched by what the operator calls a screen, not by what
   * the design document calls it: "API keys" has to answer to `key` and `token`,
   * and "Audit log" to `history`.
   */
  readonly keywords?: readonly string[] | undefined;
  readonly run: () => void;
}

/** One rendered section: the group's name and the commands the filter kept. */
export interface CommandGrouping {
  readonly group: CommandGroup;
  readonly items: readonly Command[];
}

/** DOM id for one command, so `aria-activedescendant` can point at it. */
export function commandDomId(prefix: string, id: string): string {
  // One character per replacement, not one per *run*: `nav:/admin` and
  // `nav:admin` are different commands, and collapsing runs would give them the
  // same id — which is the one thing `aria-activedescendant` cannot survive.
  return `${prefix}-${id.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
}

/**
 * How well a command answers a query: lower is better, `null` is no match.
 *
 * The ranks are what make the first result predictable — an exact label beats a
 * prefix, a prefix beats a substring, and a hint or keyword hit comes last, so
 * typing `hunt` offers the Hunt console before it offers a saved hunt whose query
 * happens to contain the word.
 */
function rank(command: Command, needle: string): number | null {
  const label = command.label.toLowerCase();
  if (label === needle) return 0;
  if (label.startsWith(needle)) return 1;
  if (label.includes(needle)) return 2;
  const words = [command.hint ?? '', ...(command.keywords ?? [])].map((word) => word.toLowerCase());
  if (words.some((word) => word.includes(needle))) return 3;
  return null;
}

/** The order the sections are shown in, which is also the filter's first key. */
export const GROUP_ORDER: readonly CommandGroup[] = ['Navigation', 'Saved hunts', 'Actions'];

/**
 * The commands a query keeps, best match first *within its section*.
 *
 * An empty query keeps everything in the order it was built, which is the order the
 * user sees before typing: navigation, then saved hunts, then actions.
 *
 * The section is the primary key, not the match quality. A palette whose sections
 * reshuffled as you typed would put "Audit log" above "Alerts" one keystroke and
 * below it the next, and an operator who has learned that the second entry is
 * Alerts would open the wrong screen; a screen order that does not move is worth
 * more than a marginal match outranking a section. Within a section the order is
 * rank, then original position — a total, stable order, so two equally good matches
 * never swap places between keystrokes.
 */
export function filterCommands(commands: readonly Command[], query: string): readonly Command[] {
  const needle = query.trim().toLowerCase();
  if (needle === '') return commands;
  const scored: { command: Command; section: number; rank: number; index: number }[] = [];
  commands.forEach((command, index) => {
    const score = rank(command, needle);
    if (score === null) return;
    const section = GROUP_ORDER.indexOf(command.group);
    scored.push({ command, section, rank: score, index });
  });
  scored.sort(
    (left, right) =>
      left.section - right.section || left.rank - right.rank || left.index - right.index,
  );
  return scored.map((entry) => entry.command);
}

/**
 * The next selection, wrapping at both ends.
 *
 * Wrapping rather than stopping: the list is short and the operator's hands are on
 * the arrows, so pressing Down on the last command landing on the first is the
 * shorter path to it than Down-arrowing the whole list.
 */
export function moveSelection(index: number, delta: number, count: number): number {
  if (count <= 0) return 0;
  return (((index + delta) % count) + count) % count;
}

/** The filter's matches, grouped for rendering, in group order of first appearance. */
export function groupCommands(commands: readonly Command[]): readonly CommandGrouping[] {
  const groups: { group: CommandGroup; items: Command[] }[] = [];
  for (const command of commands) {
    const existing = groups.find((group) => group.group === command.group);
    if (existing === undefined) {
      groups.push({ group: command.group, items: [command] });
    } else {
      existing.items.push(command);
    }
  }
  return groups;
}
