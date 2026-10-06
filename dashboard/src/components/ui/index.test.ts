/**
 * @vitest-environment node
 */
/**
 * The barrel against design.md §6 (R-22, R-27).
 *
 * §6 is the approved list, so the test reads the list out of the document and
 * asks the barrel for each name. A primitive that exists but is not exported is
 * not approved — a screen cannot import it through the barrel, and the only way
 * left is reaching into the file directly, which is exactly what R-22 forbids.
 *
 * Four §6 components are deliberately absent, because another task owns them:
 * the D3 visualisations (T-406) and the command palette (T-411). They are named
 * here rather than quietly skipped, so shipping them later means deleting a line
 * from this file.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import * as ui from './index';

const design = readFileSync(
  fileURLToPath(new URL('../../../../design.md', import.meta.url)),
  'utf8',
);

/** The component table in §6, as plain names. */
function sectionSix(): string[] {
  const start = design.indexOf('## 6. Component library');
  expect(start, 'design.md has a §6').toBeGreaterThanOrEqual(0);
  const end = design.indexOf('\n## ', start + 1);
  const body = design.slice(start, end);

  const names = body
    .split('\n')
    .filter((line) => line.startsWith('|'))
    .flatMap((line) => line.split('|')[1]?.match(/`([A-Za-z/ ]+)`/g) ?? [])
    .flatMap((cell) => cell.replaceAll('`', '').split('/'))
    .map((name) => name.trim())
    .filter((name) => /^[A-Z]/.test(name));
  return [...new Set(names)];
}

/** Owned by T-406 and T-411; §6 components, but not this task's scope. */
const OTHER_TASKS = ['Timeline', 'TimeSeriesChart', 'EntityGraph', 'CommandPalette'];

/**
 * §6 names that ship as more than one export. A toast has no standalone form —
 * the region owns the timers and the hook is the only way to raise one — so the
 * pair *is* the component.
 */
const AS_A_PAIR: Record<string, string[]> = { Toast: ['ToastProvider', 'useToast'] };

/** Whether the barrel exposes this §6 name, alone or as its documented parts. */
function shipped(name: string): boolean {
  const parts = AS_A_PAIR[name];
  return parts === undefined ? name in ui : parts.every((part) => part in ui);
}

describe('the ui barrel', () => {
  it('names every component design.md §6 lists', () => {
    expect(sectionSix()).toEqual(
      expect.arrayContaining([
        'Button',
        'Badge',
        'Card',
        'Panel',
        'DataTable',
        'Modal',
        'ConfirmDialog',
        'SeverityPill',
        'ScoreMeter',
        'Toast',
        'ConnectionStatus',
        'EmptyState',
        'ErrorState',
        'Skeleton',
      ]),
    );
  });

  it('exports each of them, except the four another task owns', () => {
    const missing = sectionSix().filter((name) => !shipped(name) && !OTHER_TASKS.includes(name));

    expect(missing).toEqual([]);
  });

  it('does not export the four early, so a screen cannot use a stub', () => {
    for (const name of OTHER_TASKS) expect(name in ui).toBe(false);
  });
});
