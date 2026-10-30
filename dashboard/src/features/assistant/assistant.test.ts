import { describe, expect, it } from 'vitest';

import { answerLabel, canAsk } from './assistant';

describe('assistant page rules', () => {
  it('labels where each kind of answer came from', () => {
    expect(answerLabel('rules')).toBe('Computed from the data');
    expect(answerLabel('openai')).toBe('Written by the local model');
    expect(answerLabel('guardrail')).toBe('Refused');
  });

  it('never hides a backend it does not know', () => {
    expect(answerLabel('mystery')).toBe('Source: mystery');
  });

  it('sends only non-blank questions within the limit', () => {
    expect(canAsk('   ')).toBe(false);
    expect(canAsk(' how many alerts ')).toBe(true);
    expect(canAsk('x'.repeat(501))).toBe(false);
  });
});
