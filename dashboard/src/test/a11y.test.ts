/**
 * @vitest-environment node
 */
/**
 * The accessibility pass's coverage contract (T-413).
 *
 * Two claims, both about the pass rather than about a screen:
 *
 *   1. **The three core screens each carry the audit.** A pass is only a pass if the
 *      screens it names are the ones being checked, and a per-screen audit is exactly
 *      the kind of thing that gets deleted in a refactor with nothing failing — the
 *      screen's own tests keep passing, and the only evidence the audit ever ran is in
 *      the file nobody reads. So the files are read here.
 *   2. **The axe helper's two levels are different.** `expectAccessible` is the gate
 *      design.md §9 sets (critical/serious); `expectAxeClean` is the stronger claim
 *      measured for the three core screens. If the second ever became an alias of the
 *      first, the stronger claim would be silently downgraded, so the rule sets are
 *      read from the sources and asserted to differ.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

// `src/`, not this file's own directory: the paths below are relative to it.
const SRC = fileURLToPath(new URL('..', import.meta.url));

/** The three core screens, and the files that audit them. */
const CORE_SCREENS = [
  ['Overview', 'features/overview/pages/OverviewPage.test.tsx'],
  ['Alert triage', 'features/triage/pages/TriagePage.test.tsx'],
  ['Hunt', 'features/hunt/pages/HuntPage.test.tsx'],
] as const;

function source(relative: string): string {
  return readFileSync(`${SRC}${relative}`, 'utf8');
}

describe('the accessibility pass (T-413)', () => {
  it('audits every core screen for structure and for keyboard reach', () => {
    for (const [name, file] of CORE_SCREENS) {
      const text = source(file);
      expect(text, `${name} has no structure audit`).toContain('auditStructure(');
      expect(text, `${name} has no keyboard audit`).toContain('auditKeyboard(');
      // The *call*, not just the import: a suite that imports the gate and never
      // awaits it has no gate, and the source contract has to be able to see that.
      expect(text, `${name} has no axe assertion`).toMatch(/await expectAccessible\(/);
    }
  });

  it('reads the same screen through the shell for its landmarks', () => {
    const shell = source('App.test.tsx');
    expect(shell).toContain('auditLandmarks(');
    // The three core routes, named: a landmark audit of one screen is not the claim.
    for (const path of ["'/'", "'/alerts'", "'/hunt'"]) {
      expect(shell, `the shell audit does not read ${path}`).toContain(path);
    }
  });

  it('keeps the strong axe claim and the shippable gate apart', () => {
    const helper = source('test/axe.ts');
    // The gate: WCAG tags only, filtered to serious and critical.
    expect(helper).toMatch(/values: \['wcag2a', 'wcag2aa', 'wcag21aa'\]/);
    expect(helper).toContain("'serious', 'critical'");
    // The strong claim: the best-practice tag set, and no impact filter at all.
    expect(helper).toContain("'best-practice'");
    const strong = helper.slice(helper.indexOf('export async function findAllViolations'));
    expect(strong).not.toContain("'serious', 'critical'");
  });
});
