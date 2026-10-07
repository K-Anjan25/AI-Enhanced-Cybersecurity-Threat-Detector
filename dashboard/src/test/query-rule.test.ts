/**
 * R-87, as a check rather than a hope (T-414).
 *
 * The rule: *frontend tests cover user-visible behaviour, not implementation details.
 * Query by role/label, not by class name or test-id-only.* A rule that only the reviewer
 * enforces decays, so this reads every test file's source and fails on the three ways a
 * test can reach past the user: `getByTestId`-style lookups, `querySelector`, and class
 * assertions.
 *
 * Three properties, in the order they matter:
 *
 *   1. **No query by test id or CSS selector, and no class assertion, unless the file
 *      declares why.** The exemptions below are paint and decoration — a shimmer bar, an
 *      SVG mark's position, an element whose whole point is `aria-hidden` — where no role
 *      or label exists to query and inventing one would be worse than the shortcut. Each
 *      carries its reason in the file.
 *   2. **An exemption has to be used.** A conversion that moves the last test-id query out
 *      of a file must delete the exemption, so the list cannot rot into a blanket licence.
 *   3. **An exempt file is never test-id-only.** Each one also queries a role or a label,
 *      which is what R-87's "not by class name or test-id-only" asks for: the paint check
 *      is an extra assertion beside a behavioural one, not the whole test.
 *
 * Reading sources is the only way to check this: a query that is *absent* from every test
 * is invisible to the suite, and the suite is what this rule governs.
 *
 * @vitest-environment node
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/** The repository's `src/`, from this file's own location. */
const SRC = new URL('..', import.meta.url);

/** A query or assertion that reaches past what the user can see. */
const IMPLEMENTATION_QUERY = /(get|find|query)(All)?ByTestId\(|querySelector(All)?\(|toHaveClass\(/;

/** Every test file under `src/`, relative and slash-separated. */
function testFiles(directory: URL, prefix = ''): string[] {
  const entries = readdirSync(directory, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const path = `${prefix}${entry.name}`;
    if (entry.isDirectory()) {
      files.push(...testFiles(new URL(`${entry.name}/`, directory), `${path}/`));
    } else if (/\.test\.tsx?$/.test(entry.name) && path !== 'test/query-rule.test.ts') {
      files.push(path);
    }
  }
  return files.sort();
}

/** What one file's test id or selector query is allowed to be, and why. */
interface Exemption {
  readonly file: string;
  readonly pattern: RegExp;
  readonly reason: string;
}

/**
 * Paint and decoration: rendering checks with no role or label to query.
 *
 * Deliberately short. If an entry's justification would be "the query is easier this way",
 * it does not belong here — the fix is to make the thing queryable, which is what the rest
 * of T-414 did to sixty-odd lookups.
 */
const EXEMPTIONS: readonly Exemption[] = [
  {
    file: 'components/ui/Card.test.tsx',
    pattern: /skeleton-bar/,
    reason:
      'the shimmer bars are decorative and `aria-hidden`; the count pins the loading shape, and the same test asserts the status role and its label',
  },
  {
    file: 'components/ui/states.test.tsx',
    pattern: /skeleton-bar|\[aria-hidden="true"\]/,
    reason:
      'the same shimmer, plus the assertion that the bars are hidden from assistive technology — which is a claim about `aria-hidden` itself',
  },
  {
    file: 'components/ui/ConnectionStatus.test.tsx',
    pattern: /\[aria-hidden="true"\]/,
    reason:
      'the glyph is hidden on purpose (the status region beside it carries the words), so the test has to look at the hidden element',
  },
  {
    file: 'components/ui/ScoreMeter.test.tsx',
    pattern: /\[aria-hidden="true"\]/,
    reason:
      'the threshold tick is painted and `aria-hidden`; its value is in the meter role, which the same file asserts',
  },
  {
    file: 'features/models/pages/DriftPage.test.tsx',
    pattern: /threshold-mark/,
    reason:
      'the mark is a line inside an `aria-hidden` bar, positioned from the threshold; the table role and the mark title are asserted beside it',
  },
  {
    file: 'features/traffic/components/BrushSeries.test.tsx',
    pattern: /brush-surface|brush-mask-|bar-|score-segment-/,
    reason:
      'SVG geometry inside a labelled `role="group"`: pointer coordinates and painted bucket counts have no accessible representation, and the group label and the slider roles are asserted in the same file',
  },
  {
    file: 'features/traffic/pages/TrafficPage.test.tsx',
    pattern: /brush-surface/,
    reason:
      'the drag that commits a brush is a pointer gesture on an SVG rect with no accessible representation; the test asserts the request the gesture caused, which is the page-level fact, and every panel it changed is queried by role',
  },
  {
    file: 'features/triage/components/TimelinePanel.test.tsx',
    pattern: /tick-[ab]/,
    reason:
      'tick positions are percentages of the span the image role already names, and `toHaveStyle` is the only way to read a painted offset',
  },
];

describe('R-87 — tests query what the user sees', () => {
  const files = testFiles(SRC);

  it('has test files to read, and reads them all', () => {
    expect(files.length).toBeGreaterThan(50);
    expect(files).toContain('features/triage/pages/TriagePage.test.tsx');
  });

  it('finds no test-id lookup, DOM query or class assertion outside the declared exemptions', () => {
    const undeclared: string[] = [];
    for (const file of files) {
      const text = readFileSync(join(SRC.pathname, file), 'utf8');
      for (const [index, line] of text.split('\n').entries()) {
        if (!IMPLEMENTATION_QUERY.test(line)) continue;
        const allowed = EXEMPTIONS.some(
          (exemption) => exemption.file === file && exemption.pattern.test(line),
        );
        if (!allowed) undeclared.push(`${file}:${String(index + 1)} ${line.trim()}`);
      }
    }
    expect(
      undeclared,
      'query by role or label instead, or add an exemption with its reason',
    ).toEqual([]);
  });

  it('uses every exemption, so the list cannot rot into a licence', () => {
    const unused: string[] = [];
    for (const exemption of EXEMPTIONS) {
      const text = readFileSync(join(SRC.pathname, exemption.file), 'utf8');
      const used = text
        .split('\n')
        .some((line) => IMPLEMENTATION_QUERY.test(line) && exemption.pattern.test(line));
      if (!used) unused.push(`${exemption.file} (${exemption.pattern.source})`);
    }
    expect(unused, 'delete the exemption the conversion made obsolete').toEqual([]);
  });

  it('never exempts a test from querying a role or a label as well', () => {
    const idOnly: string[] = [];
    for (const exemption of EXEMPTIONS) {
      const text = readFileSync(join(SRC.pathname, exemption.file), 'utf8');
      const queriesByRole = /(get|find|query)(All)?By(Role|LabelText)\(/.test(text);
      if (!queriesByRole) idOnly.push(`${exemption.file}: ${exemption.reason}`);
    }
    expect(idOnly, 'a paint check stands beside a behavioural query, never alone').toEqual([]);
  });
});
