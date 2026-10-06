import { describe, expect, it } from 'vitest';

import {
  isVerdictName,
  VERDICT_LABELS,
  VERDICT_SHORTCUTS,
  verdictForKey,
  verdictLabel,
  VERDICTS,
} from './verdicts';

describe('verdict vocabulary', () => {
  it('numbers the shortcuts 1, 2, 3 in the bar order', () => {
    // FR-51 names the keys; the order is design.md §4.3's.
    expect(VERDICT_SHORTCUTS.map((shortcut) => shortcut.key)).toEqual(['1', '2', '3']);
    expect(VERDICT_SHORTCUTS.map((shortcut) => shortcut.verdict)).toEqual([
      'true_positive',
      'false_positive',
      'benign',
    ]);
  });

  it('maps a key to the verdict the button beside it records', () => {
    // The key and the button must not be able to disagree, so both read this table.
    for (const shortcut of VERDICT_SHORTCUTS) {
      expect(verdictForKey(shortcut.key)).toBe(shortcut.verdict);
      expect(shortcut.label).toBe(VERDICT_LABELS[shortcut.verdict]);
    }
  });

  it('has no verdict for a key that is not a shortcut', () => {
    expect(verdictForKey('4')).toBeNull();
    expect(verdictForKey('a')).toBeNull();
    expect(verdictForKey('')).toBeNull();
  });

  it('recognises exactly the three verdicts it sends', () => {
    expect(VERDICTS).toHaveLength(3);
    expect(isVerdictName('benign')).toBe(true);
    expect(isVerdictName('false_positives')).toBe(false);
    expect(isVerdictName('')).toBe(false);
  });

  it('renders a verdict it does not know as itself', () => {
    // A verdict written by a later build must still be readable on screen.
    expect(verdictLabel('true_positive')).toBe('True positive');
    expect(verdictLabel('escalated')).toBe('escalated');
  });

  it('sends the wire names, not the labels', () => {
    expect(VERDICT_LABELS.true_positive).not.toBe('true_positive');
    expect(VERDICT_SHORTCUTS[0]?.verdict).toBe('true_positive');
  });
});
