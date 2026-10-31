import { describe, expect, it } from 'vitest';

import { canStart, describeRequest, orderEngines, toggleEngine } from './capture';

describe('capture panel rules', () => {
  it('keeps the catalogue order whatever order the engines were chosen in', () => {
    expect(orderEngines(['tshark', 'suricata'])).toEqual(['suricata', 'tshark']);
  });

  it('adds and removes an engine without reordering the rest', () => {
    expect(toggleEngine(['suricata'], 'tshark')).toEqual(['suricata', 'tshark']);
    expect(toggleEngine(['suricata', 'tshark'], 'suricata')).toEqual(['tshark']);
  });

  it('ignores an engine it does not know', () => {
    expect(toggleEngine(['suricata'], 'snort')).toEqual(['suricata']);
    // Zeek left the image: an old saved choice of it is ignored, not offered.
    expect(orderEngines(['zeek', 'suricata'])).toEqual(['suricata']);
  });

  it('will not start with no engine chosen, but may always stop', () => {
    expect(canStart([])).toBe(false);
    expect(canStart(['suricata'])).toBe(true);
  });

  it('describes a request, not a running sensor', () => {
    expect(describeRequest({ running: true, engines: ['tshark', 'suricata'] })).toBe(
      'Capture is requested on suricata, tshark. The sensor starts them within a few seconds.',
    );
    expect(describeRequest({ running: false, engines: [] })).toBe(
      'Capture is stopped. The sensor stops its engines within a few seconds.',
    );
  });
});
