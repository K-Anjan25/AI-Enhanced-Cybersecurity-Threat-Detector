/**
 * @vitest-environment node
 */
/**
 * The audit model (T-410, FR-42, R-37).
 *
 * Two claims get the weight here. The CSV escaping, because an unescaped comma shifts
 * every later column and an export that misattributes an actor is worse than no export;
 * and the "non-editable" half of §4.8, which is a property of this module's *surface*
 * rather than of any one function — so the test reads the module's exports and asserts
 * that nothing in them is a writer.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import type { AuditEntry } from '../../api/admin';
import {
  AUDIT_ACTION_CHOICES,
  DEFAULT_AUDIT_HOURS,
  auditCsv,
  auditNote,
  auditRows,
  csvField,
  formatDetail,
} from './audit';

function entry(over: Partial<AuditEntry> = {}): AuditEntry {
  return {
    id: 91,
    actor: 'ops@example.test',
    action: 'threshold.set',
    target_type: 'threshold',
    target_id: 'flow/high',
    detail: { previous: 0.7, applied: 0.8 },
    ip: '10.0.0.7',
    at: '2026-10-06T10:00:00Z',
    ...over,
  };
}

describe('auditRows', () => {
  it('flattens the detail with sorted keys so the same context reads the same way', () => {
    const rows = auditRows([entry({ detail: { applied: 0.8, previous: 0.7 } })]);
    expect(rows[0]?.detail).toBe('applied=0.8 previous=0.7');
  });

  it('renders an array detail as a joined list and an empty one as a dash', () => {
    expect(auditRows([entry({ detail: { scopes: ['a', 'b'] } })])[0]?.detail).toBe('scopes=a|b');
    expect(auditRows([entry({ detail: {} })])[0]?.detail).toBe('—');
  });

  it('names a target as type:id', () => {
    expect(auditRows([entry()])[0]?.target).toBe('threshold:flow/high');
  });

  it('says an absent source IP was not recorded rather than leaving a blank cell', () => {
    expect(auditRows([entry({ ip: null })])[0]?.ip).toBe('not recorded');
  });

  it('is empty for an unread page', () => {
    expect(auditRows(undefined)).toEqual([]);
  });
});

describe('formatDetail', () => {
  it('stringifies a nested value rather than dropping the field', () => {
    expect(formatDetail({ nested: { a: 1 } })).toBe('nested=[object Object]');
  });
});

describe('auditNote', () => {
  it('says the window is fully read when the cursor is exhausted', () => {
    const note = auditNote(3, false);
    expect(note).toContain('3 entries in this window, newest first.');
    expect(note).toContain('fully read');
  });

  it('says the page cap was reached and that nothing was dropped', () => {
    // The difference between "this is the window" and "this is the first page of it"
    // is the difference between an answer and a half-answer.
    const note = auditNote(50, true);
    expect(note).toContain('page cap was reached');
    expect(note).toContain('not dropped');
  });

  it('states the append-only rule in the sentence under the table', () => {
    expect(auditNote(1, false)).toContain('no edit or delete anywhere, in any role');
  });
});

describe('csv escaping', () => {
  it('quotes a field that contains a comma', () => {
    expect(csvField('a,b')).toBe('"a,b"');
  });

  it('doubles a quote inside a quoted field', () => {
    expect(csvField('say "hi"')).toBe('"say ""hi"""');
  });

  it('quotes a field with a newline, which would otherwise split the row', () => {
    expect(csvField('a\nb')).toBe('"a\nb"');
  });

  it('leaves an ordinary field alone', () => {
    expect(csvField('ops@example.test')).toBe('ops@example.test');
  });
});

describe('auditCsv', () => {
  it('writes a header and one line per row, in the table’s order', () => {
    const csv = auditCsv(auditRows([entry(), entry({ id: 90, action: 'key.revoke' })]));
    const lines = csv.trimEnd().split('\n');
    expect(lines).toHaveLength(3);
    expect(lines[0]).toBe('id,at,actor,action,target,detail,ip');
    expect(lines[1]?.startsWith('91,')).toBe(true);
    expect(lines[2]).toContain('key.revoke');
  });

  it('keeps a comma inside one column instead of shifting the rest', () => {
    // The failure this prevents: an actor field carrying a comma would push every
    // later value one column left, so the export would name the wrong actor.
    const csv = auditCsv(auditRows([entry({ actor: 'ops, on call' })]));
    const fields = csv.trimEnd().split('\n')[1] ?? '';
    expect(fields).toContain('"ops, on call"');
    expect(fields.endsWith(',10.0.0.7')).toBe(true);
  });

  it('ends with a newline, so a row is never half-written', () => {
    expect(auditCsv(auditRows([entry()])).endsWith('\n')).toBe(true);
    expect(auditCsv([])).toBe('id,at,actor,action,target,detail,ip\n');
  });
});

describe('the filter vocabulary', () => {
  it('offers every action this build records, plus "any"', () => {
    const values = AUDIT_ACTION_CHOICES.map((choice) => choice.value);
    expect(values[0]).toBe('');
    for (const action of [
      'threshold.set',
      'user.role',
      'key.create',
      'key.revoke',
      'model.promote',
      'hunt.export',
    ]) {
      expect(values).toContain(action);
    }
    expect(new Set(values).size).toBe(values.length);
  });

  it('defaults to a bounded window the route accepts', () => {
    expect(DEFAULT_AUDIT_HOURS).toBe(24);
  });
});

describe('non-editability is structural', () => {
  it('exports no function that could write to the trail', () => {
    // §4.8's "no edit affordance anywhere" is a property of the surface, so the
    // surface is what the test reads: the module names nothing that mutates.
    const source = readFileSync(fileURLToPath(new URL('./audit.ts', import.meta.url)), 'utf8');
    const exported = [...source.matchAll(/export (?:async )?function (\w+)/g)].map(
      (m) => m[1] ?? '',
    );
    expect(exported).toEqual(['auditRows', 'formatDetail', 'auditNote', 'auditCsv', 'csvField']);
    for (const name of exported) {
      expect(name).not.toMatch(/update|edit|delete|remove|patch|purge|truncate/i);
    }
  });
});
