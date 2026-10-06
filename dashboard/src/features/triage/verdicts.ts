/**
 * The verdict vocabulary and its keyboard shortcuts (FR-16, design.md §4.3).
 *
 * One table, because three things must agree about it and only one of them is a
 * rendering:
 *
 *   * the three buttons in the sticky bar and the labels beside them;
 *   * the keyboard shortcuts `1`/`2`/`3` — FR-51's "full triage loop completable
 *     without a mouse" is only true if the key and the button send the *same*
 *     verdict, so they are read from this table rather than written twice;
 *   * the values sent to `POST /alerts/{id}/verdict`, which are the wire form and
 *     must not drift from the labels.
 *
 * The order is the design's order — true positive, false positive, benign — and it
 * is also the order the keys are numbered in. Reordering the array renumbers the
 * shortcuts, which is why the keys are numbered from the array rather than
 * hard-coded per entry.
 */

/** The verdicts an analyst can record, in the bar's order. */
export const VERDICTS = ['true_positive', 'false_positive', 'benign'] as const;

export type VerdictName = (typeof VERDICTS)[number];

/** What each verdict is called on screen. */
export const VERDICT_LABELS: Record<VerdictName, string> = {
  true_positive: 'True positive',
  false_positive: 'False positive',
  benign: 'Benign',
};

/** One bar button: the key, the verdict it records, and its label. */
export interface VerdictShortcut {
  /** The digit that records it, `1`-`3`, in `VERDICTS` order. */
  key: string;
  verdict: VerdictName;
  label: string;
}

/** The three shortcuts, numbered by position. */
export const VERDICT_SHORTCUTS: readonly VerdictShortcut[] = VERDICTS.map((verdict, index) => ({
  key: String(index + 1),
  verdict,
  label: VERDICT_LABELS[verdict],
}));

/** The verdict a pressed key records, or `null` when the key is not a shortcut. */
export function verdictForKey(key: string): VerdictName | null {
  return VERDICT_SHORTCUTS.find((shortcut) => shortcut.key === key)?.verdict ?? null;
}

/** Whether a string from the API names a verdict this build knows. */
export function isVerdictName(value: string): value is VerdictName {
  return (VERDICTS as readonly string[]).includes(value);
}

/**
 * A verdict's label, for a value that came from the API.
 *
 * An unrecognised value renders as itself rather than being swallowed: a verdict
 * recorded by a later version of the backend must show up as *something the
 * analyst can read*, even if this build cannot name it.
 */
export function verdictLabel(verdict: string): string {
  return isVerdictName(verdict) ? VERDICT_LABELS[verdict] : verdict;
}
