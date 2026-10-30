import { describe, expect, it } from 'vitest';

import { canStart, describeRequest, orderEngines, toggleEngine } from './capture';

describe('capture panel rules', () => {
  it('keeps the catalogue order whatever order the engines were chosen in', () => {
    expect(orderEngines(['tshark', 'zeek'])).toEqual(['zeek', 'tshark']);
  });

  it('adds and removes an engine without reordering the rest', () => {
    expect(toggleEngine(['zeek'], 'suricata')).toEqual(['zeek', 'suricata']);
    expect(toggleEngine(['zeek', 'suricata'], 'zeek')).toEqual(['suricata']);
  });

  it('ignores an engine it does not know', () => {
    expect(toggleEngine(['zeek'], 'snort')).toEqual(['zeek']);
  });

  it('will not start with no engine chosen, but may always stop', () => {
    expect(canStart([])).toBe(false);
    expect(canStart(['suricata'])).toBe(true);
  });

  it('describes a request, not a running sensor', () => {
    expect(describeRequest({ running: true, engines: ['suricata', 'zeek'] })).toBe(
      'Capture is requested on zeek, suricata. The sensor starts them within a few seconds.',
    );
    expect(describeRequest({ running: false, engines: [] })).toBe(
      'Capture is stopped. The sensor stops its engines within a few seconds.',
    );
  });
});
