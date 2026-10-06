/**
 * axe-core accessibility assertions (NFR-09).
 *
 * CI catches what is automatable; a manual screen-reader pass is still required
 * per release (design.md §9).
 */
import axe, { type Result } from 'axe-core';

/** Run axe on a container and return serious-or-worse violations. */
export async function findViolations(container: HTMLElement): Promise<Result[]> {
  const results = await axe.run(container, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] },
  });
  return results.violations.filter((violation) =>
    ['serious', 'critical'].includes(violation.impact ?? ''),
  );
}

/**
 * Every violation axe reports, at every impact level, including best-practice rules.
 *
 * Maintained separately from `findViolations` because the two answer different
 * questions: that one is the standing gate ("no critical/serious"), and this one is the
 * stronger claim the three core screens can make — nothing at all, not even a
 * best-practice advisory. T-413 measured it before asserting it: all three screens
 * report zero violations with the `best-practice` tag set included, so the assertion
 * records a fact rather than an aspiration.
 */
export async function findAllViolations(container: HTMLElement): Promise<Result[]> {
  const results = await axe.run(container, {
    runOnly: {
      type: 'tag',
      values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa', 'best-practice'],
    },
  });
  return results.violations;
}

/** Assert axe reports nothing at all — no impact level, no tag set. */
export async function expectAxeClean(container: HTMLElement): Promise<void> {
  const violations = await findAllViolations(container);
  if (violations.length > 0) {
    const summary = violations
      .map(
        (violation) =>
          `${violation.id} (${violation.impact ?? 'none'}): ${violation.help} (${String(violation.nodes.length)} nodes)`,
      )
      .join('\n  ');
    throw new Error(`Accessibility violations at some impact level:\n  ${summary}`);
  }
}

/** Assert an element has no serious or critical WCAG 2.1 AA violations. */
export async function expectAccessible(container: HTMLElement): Promise<void> {
  const violations = await findViolations(container);
  if (violations.length > 0) {
    const summary = violations
      .map((violation) => `${violation.id}: ${violation.help} (${violation.nodes.length} nodes)`)
      .join('\n  ');
    throw new Error(`Accessibility violations:\n  ${summary}`);
  }
}
