/**
 * The query language, without a DOM in sight.
 *
 * The cases here are the ones that decide whether the console can be trusted: an
 * unknown field is refused rather than dropped, a repeated field names the fix, a
 * value outside a closed vocabulary is refused with the vocabulary, and the echo is
 * canonical — the parse re-serialised, including the parts the analyst did not type.
 * A parser that quietly ignored a term would pass a rendering test and still be the
 * wrong instrument.
 */
import { describe, expect, it } from 'vitest';

import {
  buildHuntParams,
  describeHunt,
  huntCompletions,
  huntField,
  huntWindow,
  parseHuntQuery,
  spanOf,
  HUNT_DEFAULTS,
  HUNT_FIELDS,
  HUNT_SPANS,
  UNSEARCHABLE_TERMS,
} from './query';

const WINDOW = { start: new Date('2026-10-05T10:00:00Z'), end: new Date('2026-10-06T10:00:00Z') };

describe('the vocabulary', () => {
  it('is the alert read model’s filter set, and nothing else', () => {
    expect(HUNT_FIELDS.map((field) => field.name)).toEqual([
      'severity',
      'status',
      'family',
      'entity',
      'min_score',
      'order',
      'limit',
    ]);
    // Every field names the API parameter it sets: the console's words and the
    // wire's words are the same list, in the same order, in one place.
    expect(HUNT_FIELDS.map((field) => field.param)).toEqual([
      'severity',
      'status',
      'family',
      'entityId',
      'minScore',
      'order',
      'limit',
    ]);
  });

  it('names the fields §4.6 suggests that this build cannot search', () => {
    expect(UNSEARCHABLE_TERMS.map((term) => term.name)).toEqual([
      'src_ip',
      'dst_port',
      'template_id',
      'message',
      'trace',
    ]);
    // Each refusal says why, and the reasons point at the tasks that would change
    // the answer rather than at the console's own shortcoming.
    for (const term of UNSEARCHABLE_TERMS) {
      expect(term.reason.length).toBeGreaterThan(20);
    }
  });

  it('treats family as free text, because the labels are data', () => {
    expect(huntField('family')?.values).toBeNull();
  });

  it('treats the row cap as a range with suggestions, not a menu', () => {
    expect(huntField('limit')?.values).toBeNull();
    expect(huntField('limit')?.suggestions).toEqual(['100', '500', '1000']);
  });
});

describe('parseHuntQuery', () => {
  it('reads fields, values and commas', () => {
    const parse = parseHuntQuery(
      'severity:high,critical family:exfiltration entity:42 min_score:0.75',
    );

    expect(parse.errors).toEqual([]);
    expect(parse.terms.map((term) => [term.field.name, term.values])).toEqual([
      ['severity', ['high', 'critical']],
      ['family', ['exfiltration']],
      ['entity', ['42']],
      ['min_score', ['0.75']],
    ]);
  });

  it('normalises a closed vocabulary to the API’s spelling', () => {
    const parse = parseHuntQuery('severity:HIGH status:Open order:DESC');
    expect(parse.errors).toEqual([]);
    expect(parse.terms.map((term) => term.values)).toEqual([['high'], ['open'], ['desc']]);
  });

  it('refuses a field it cannot search, and says which it can', () => {
    const parse = parseHuntQuery('src_ip:10.0.0.7');

    expect(parse.terms).toEqual([]);
    expect(parse.errors).toHaveLength(1);
    expect(parse.errors[0]?.token).toBe('src_ip:10.0.0.7');
    expect(parse.errors[0]?.reason).toContain('not a field this build can search');
    expect(parse.errors[0]?.reason).toContain('severity');
  });

  it('refuses a term with no field rather than searching everything', () => {
    const parse = parseHuntQuery('exfiltration');
    expect(parse.errors[0]?.reason).toContain('field:value');
  });

  it('refuses a field with no value, and names the shape it wants', () => {
    const parse = parseHuntQuery('severity:');
    expect(parse.errors[0]?.reason).toBe('severity needs a value, as in severity:high,critical');
  });

  it('refuses a field set twice, and names the comma form that works', () => {
    const parse = parseHuntQuery('severity:high severity:low');

    expect(parse.terms.map((term) => term.values)).toEqual([['high']]);
    expect(parse.errors).toHaveLength(1);
    expect(parse.errors[0]?.reason).toBe('severity is set twice. Write severity:low,high instead');
  });

  it('refuses a value outside a closed vocabulary and lists the vocabulary', () => {
    const parse = parseHuntQuery('severity:urgent');
    expect(parse.errors[0]?.reason).toContain('“urgent” is not one of them');
    expect(parse.errors[0]?.reason).toContain('critical');
  });

  it('refuses a number where the API takes an integer', () => {
    expect(parseHuntQuery('entity:web-1').errors[0]?.reason).toContain('whole number');
    expect(parseHuntQuery('limit:lots').errors[0]?.reason).toContain('whole number');
  });

  it('refuses a row cap the API would refuse', () => {
    expect(parseHuntQuery('limit:0').errors[0]?.reason).toContain('1 to 1,000');
    expect(parseHuntQuery('limit:5000').errors[0]?.reason).toContain('1 to 1,000');
    expect(parseHuntQuery('limit:1000').errors).toEqual([]);
  });

  it('accepts a row cap between the round numbers, because the API does', () => {
    // The suggested values are suggestions: `limit` is a range, not a menu, and a
    // console that refused 750 would be inventing a rule the API does not have.
    expect(parseHuntQuery('limit:750').errors).toEqual([]);
    expect(buildHuntParams(parseHuntQuery('limit:750'), WINDOW)?.limit).toBe(750);
  });

  it('refuses a score outside 0 to 1', () => {
    expect(parseHuntQuery('min_score:1.5').errors[0]?.reason).toBe('min_score runs from 0 to 1');
    expect(parseHuntQuery('min_score:abc').errors[0]?.reason).toContain('takes a number');
  });

  it('keeps the terms it did understand alongside the errors', () => {
    const parse = parseHuntQuery('status:open nonsense severity:high');
    expect(parse.terms.map((term) => term.field.name)).toEqual(['status', 'severity']);
    expect(parse.errors.map((error) => error.token)).toEqual(['nonsense']);
  });

  it('is empty for an empty box, with no error', () => {
    expect(parseHuntQuery('   ')).toEqual({ terms: [], errors: [] });
  });

  it('an empty query is legal — it searches everything in the window', () => {
    expect(buildHuntParams(parseHuntQuery(''), WINDOW)).toEqual({
      start: WINDOW.start,
      end: WINDOW.end,
      order: HUNT_DEFAULTS.order,
      limit: HUNT_DEFAULTS.limit,
    });
  });
});

describe('buildHuntParams', () => {
  it('maps the console’s fields onto the API’s parameters', () => {
    const params = buildHuntParams(
      parseHuntQuery(
        'severity:high,critical status:open family:exfiltration entity:42 min_score:0.75 limit:500 order:asc',
      ),
      WINDOW,
    );

    expect(params).toEqual({
      start: WINDOW.start,
      end: WINDOW.end,
      severity: 'high,critical',
      status: 'open',
      family: 'exfiltration',
      entityId: 42,
      minScore: 0.75,
      order: 'asc',
      limit: 500,
    });
  });

  it('applies the same defaults the API does, so the echo is the truth', () => {
    const params = buildHuntParams(parseHuntQuery('status:open'), WINDOW);
    expect(params?.order).toBe('desc');
    expect(params?.limit).toBe(100);
  });

  it('refuses to build anything from a parse with an error', () => {
    // Half a query is not a query: running the readable terms would search
    // something the analyst did not ask for.
    expect(buildHuntParams(parseHuntQuery('severity:high src_ip:10.0.0.7'), WINDOW)).toBeNull();
  });

  it('cannot express a cursor', () => {
    const params = buildHuntParams(parseHuntQuery('status:open'), WINDOW);
    expect(params).not.toHaveProperty('cursor');
  });
});

describe('describeHunt', () => {
  it('echoes the executed query with the defaults made explicit', () => {
    expect(describeHunt(parseHuntQuery('severity:high family:exfiltration'))).toBe(
      'severity:high family:exfiltration order:desc limit:100',
    );
  });

  it('echoes the normalised spelling, not the keystrokes', () => {
    expect(describeHunt(parseHuntQuery('SEVERITY:High order:asc limit:500'))).toBe(
      'severity:high order:asc limit:500',
    );
  });

  it('keeps the analyst’s order, so the echo reads like what they wrote', () => {
    expect(describeHunt(parseHuntQuery('family:x severity:low'))).toBe(
      'family:x severity:low order:desc limit:100',
    );
  });

  it('describes an empty query as the two defaults it actually runs', () => {
    expect(describeHunt(parseHuntQuery(''))).toBe('order:desc limit:100');
  });
});

describe('huntCompletions', () => {
  it('suggests fields by prefix', () => {
    const suggestions = huntCompletions('sev', 3);
    expect(suggestions).toEqual([
      { value: 'severity:', detail: 'severity:high,critical', kind: 'field' },
    ]);
  });

  it('suggests every field for an empty token rather than nothing', () => {
    expect(huntCompletions('', 0).map((suggestion) => suggestion.value)).toEqual(
      HUNT_FIELDS.map((field) => `${field.name}:`),
    );
  });

  it('suggests a field this build cannot search, with the reason', () => {
    const [suggestion] = huntCompletions('src', 3);
    expect(suggestion?.value).toBe('src_ip:');
    expect(suggestion?.kind).toBe('unsearchable');
    expect(suggestion?.detail).toContain('T-418');
  });

  it('suggests values for an open field without closing it', () => {
    // The suggestion *replaces the token*, so it is a whole value that starts with
    // what was typed — and 750, which is legal, simply has no suggestion.
    const suggestions = huntCompletions('limit:5', 'limit:5'.length);
    expect(suggestions.map((suggestion) => suggestion.value)).toEqual(['limit:500']);
    expect(huntCompletions('limit:7', 'limit:7'.length)).toEqual([]);
  });

  it('suggests the values a closed field takes, minus the ones already written', () => {
    const suggestions = huntCompletions('severity:high,', 'severity:high,'.length);
    expect(suggestions.map((suggestion) => suggestion.value)).toContain('severity:high,critical');
    expect(suggestions.map((suggestion) => suggestion.value)).not.toContain('severity:high,high');
  });

  it('offers nothing for free text, because there is no list to offer', () => {
    expect(huntCompletions('family:exf', 'family:exf'.length)).toEqual([]);
  });

  it('only completes the token the caret is in', () => {
    const text = 'status:open sev';
    const suggestions = huntCompletions(text, text.length);
    expect(suggestions.map((suggestion) => suggestion.value)).toEqual(['severity:']);
  });

  it('completes the term at the caret, not the last term in the box', () => {
    // The analyst has put the caret back inside an earlier term to finish it. A
    // completion that read the *last* space would offer fields for the whole text
    // and silently rewrite the wrong token when accepted.
    const text = 'severity:hi status:open';
    const suggestions = huntCompletions(text, 'severity:hi'.length);
    expect(suggestions.map((suggestion) => suggestion.value)).toEqual(['severity:high']);
  });
});

describe('windows', () => {
  it('offers four spans, none wider than the API will serve', () => {
    expect(HUNT_SPANS.map((span) => span.key)).toEqual(['24h', '7d', '30d', '90d']);
    const widest = Math.max(...HUNT_SPANS.map((span) => span.spanMs));
    expect(widest / 86_400_000).toBeLessThan(92);
  });

  it('snapshots a window from a clock and a span', () => {
    const now = Date.parse('2026-10-06T10:00:00Z');
    const window = huntWindow('24h', now);
    expect(window.end.toISOString()).toBe('2026-10-06T10:00:00.000Z');
    expect(window.start.toISOString()).toBe('2026-10-05T10:00:00.000Z');
  });

  it('falls back to the first span rather than throwing on an unknown key', () => {
    expect(spanOf('nope' as '24h').key).toBe('24h');
  });
});
