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
