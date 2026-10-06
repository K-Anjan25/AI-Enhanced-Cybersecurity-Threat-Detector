import { describe, expect, it } from 'vitest';

import {
  backoffDelay,
  closeDetail,
  closeVerdict,
  connectionStateOf,
  cursorOf,
  framesFromNotifications,
  parseFrame,
  socketUrl,
  stalenessLabel,
  type RealtimeFrame,
} from './realtime';

const ALERT = {
  id: 7,
  created_at: '2026-10-06T10:00:00Z',
  entity_id: 3,
  family: 'exfiltration',
  severity: 'high',
  score: 0.91,
  status: 'open',
  first_seen: '2026-10-06T09:59:00Z',
  last_seen: '2026-10-06T10:00:00Z',
  occurrence_count: 4,
  trace_id: 'abc',
};

describe('parseFrame', () => {
  it('reads a ready frame, including where the cursor stands', () => {
    const frame = parseFrame({
      type: 'ready',
      epoch: 'e-1',
      latest: 12,
      oldest_available: 4,
      resync_required: true,
      after: 3,
      heartbeat_seconds: 15,
    });

    expect(frame).toEqual({
      type: 'ready',
      epoch: 'e-1',
      latest: 12,
      oldest_available: 4,
      resync_required: true,
      after: 3,
      heartbeat_seconds: 15,
    });
  });

  it('reads an alert frame with its sequence', () => {
    expect(parseFrame({ type: 'alert', sequence: 9, alert: ALERT })).toEqual({
      type: 'alert',
      sequence: 9,
      alert: ALERT,
    });
  });

  it('keeps the stream alive when a frame is not one this build knows', () => {
    // A newer server, a truncated payload, a keep-alive the client did not ask
    // for — none of them is a reason to tear down a working connection.
    for (const unknown of [
      { type: 'future-frame', payload: 1 },
      { type: 'alert', sequence: 9 },
      { type: 'alert', sequence: 'nine', alert: ALERT },
      { type: 'alert', sequence: 9, alert: { ...ALERT, score: 'high' } },
      { type: 'alert', sequence: 9, alert: null },
      'not-json-object',
      [1, 2, 3],
      null,
      42,
    ]) {
      expect(parseFrame(unknown)).toBeNull();
    }
  });

  it('falls back to the documented heartbeat when the server does not say', () => {
    const frame = parseFrame({ type: 'ready' });

    expect(frame).toMatchObject({ type: 'ready', heartbeat_seconds: 15, resync_required: false });
  });

  it('never lets a bad heartbeat interval shorten the silence watchdog', () => {
    // Zero or negative would mean "close the socket the instant it opens".
    expect(parseFrame({ type: 'ready', heartbeat_seconds: 0 })).toMatchObject({
      heartbeat_seconds: 15,
    });
    expect(parseFrame({ type: 'ready', heartbeat_seconds: -5 })).toMatchObject({
      heartbeat_seconds: 15,
    });
  });

  it('reports a drop with the cursor to resume from', () => {
    expect(parseFrame({ type: 'dropped', reason: 'slow reader', after: 21 })).toEqual({
      type: 'dropped',
      reason: 'slow reader',
      after: 21,
    });
  });
});

describe('cursorOf', () => {
  const alert = (sequence: number): RealtimeFrame => ({ type: 'alert', sequence, alert: ALERT });

  it('is the largest sequence seen, not the last one', () => {
    expect(cursorOf([alert(5), alert(3)])).toBe(5);
  });

  it('ignores frames that carry no position', () => {
    const frames: RealtimeFrame[] = [
      { type: 'heartbeat', at: '2026-10-06T10:00:00Z' },
      {
        type: 'ready',
        epoch: 'e',
        latest: 9,
        oldest_available: 1,
        resync_required: false,
        after: 9,
        heartbeat_seconds: 15,
      },
    ];

    expect(cursorOf(frames, 4)).toBe(4);
  });

  it('is null when there was no position and nothing arrived', () => {
    expect(cursorOf([])).toBeNull();
  });

  it('never moves a cursor backwards', () => {
    // A reconnect asks the server to resume from this value; a cursor that went
    // backwards would replay alerts an analyst has already judged.
    expect(cursorOf([alert(2)], 30)).toBe(30);
  });
});

describe('framesFromNotifications', () => {
  it('turns a poll answer into the frames the socket would have sent', () => {
    const frames = framesFromNotifications(
      {
        items: [
          { sequence: 4, alert: ALERT },
          { sequence: 5, alert: ALERT },
        ],
        oldest_available: 1,
        latest: 5,
        resync_required: false,
        epoch: 'e-2',
      },
      3,
    );

    expect(frames[0]).toMatchObject({ type: 'ready', after: 3, latest: 5, epoch: 'e-2' });
    expect(frames.slice(1)).toEqual([
      { type: 'alert', sequence: 4, alert: ALERT },
      { type: 'alert', sequence: 5, alert: ALERT },
    ]);
    // All three transports hand the client the same position, which is what makes
    // switching between them invisible above this function.
    expect(cursorOf(frames, 3)).toBe(5);
  });

  it('says nothing arrived without losing the fact that the server answered', () => {
    const frames = framesFromNotifications(
      { items: [], oldest_available: 2, latest: 2, resync_required: true, epoch: 'e-2' },
      null,
    );

    expect(frames).toHaveLength(1);
    expect(frames[0]).toMatchObject({ type: 'ready', resync_required: true, latest: 2 });
  });
});

describe('backoffDelay', () => {
  it('grows the window exponentially and caps it', () => {
    const window = (attempt: number) =>
      backoffDelay(attempt, () => 1, { baseMs: 500, maxMs: 30_000 });

    expect([window(0), window(1), window(2), window(3)]).toEqual([500, 1_000, 2_000, 4_000]);
    expect(window(20)).toBe(30_000);
  });

  it('never returns more than the window or less than half of it', () => {
    // Equal jitter: half fixed, half random. A thousand dashboards reconnecting
    // after a deploy must not arrive together, and one must still retry soon.
    for (const random of [0, 0.25, 0.5, 0.99, 1]) {
      const delay = backoffDelay(3, () => random, { baseMs: 500, maxMs: 30_000 });
      expect(delay).toBeGreaterThanOrEqual(2_000);
      expect(delay).toBeLessThanOrEqual(4_000);
    }
  });

  it('treats a broken attempt number as the first attempt', () => {
    expect(backoffDelay(-3, () => 0)).toBe(250);
    expect(backoffDelay(Number.NaN, () => 0)).toBe(250);
  });
});

describe('closeVerdict', () => {
  it('stops on a refused credential, because waiting cannot fix it', () => {
    expect(closeVerdict(4401)).toBe('terminal');
    expect(closeVerdict(4403)).toBe('terminal');
  });

  it('retries on everything else, including a clean close with no reason', () => {
    for (const code of [1000, 1001, 1006, 1013, 1011]) {
      expect(closeVerdict(code)).toBe('transient');
    }
  });

  it('names the reason, so the banner can say what happened', () => {
    expect(closeDetail(4401)).toBe('The session is not authenticated');
    expect(closeDetail(4403)).toBe('This account may not read alerts');
    expect(closeDetail(1013)).toBe('The server dropped a slow reader');
    expect(closeDetail(1006)).toBe('The connection closed (1006)');
  });
});

describe('socketUrl', () => {
  const location = { protocol: 'http:', host: 'localhost:5173' };

  it('is same-origin, and upgrades with the page', () => {
    expect(socketUrl('/api/v1/alerts/ws', {}, location)).toBe(
      'ws://localhost:5173/api/v1/alerts/ws',
    );
    expect(socketUrl('/api/v1/alerts/ws', {}, { protocol: 'https:', host: 'aegis.example' })).toBe(
      'wss://aegis.example/api/v1/alerts/ws',
    );
  });

  it('drops absent parameters rather than sending them empty', () => {
    expect(socketUrl('/ws', { after: undefined }, location)).toBe('ws://localhost:5173/ws');
    expect(socketUrl('/ws', { after: 0 }, location)).toBe('ws://localhost:5173/ws?after=0');
  });

  it('refuses a path that is not on this origin', () => {
    expect(() => socketUrl('ws://elsewhere/ws', {}, location)).toThrow(/absolute path/);
  });
});

describe('connectionStateOf', () => {
  it('maps the four client states onto the three the indicator carries', () => {
    expect(connectionStateOf('live')).toBe('live');
    expect(connectionStateOf('connecting')).toBe('degraded');
    expect(connectionStateOf('polling')).toBe('disconnected');
    expect(connectionStateOf('refused')).toBe('disconnected');
  });
});

describe('stalenessLabel', () => {
  const now = Date.parse('2026-10-06T10:00:00Z');

  it('says what design.md §8.1 asks for: last update 2 m ago', () => {
    expect(stalenessLabel(now - 120_000, now)).toBe('last update 2 m ago');
  });

  it('uses seconds under a minute and hours beyond one', () => {
    expect(stalenessLabel(now - 5_000, now)).toBe('last update 5 s ago');
    expect(stalenessLabel(now - 3 * 3_600_000, now)).toBe('last update 3 h ago');
  });

  it('says there is no update yet rather than inventing one', () => {
    expect(stalenessLabel(null, now)).toBe('no update yet');
  });

  it('never shows a negative age when clocks disagree', () => {
    expect(stalenessLabel(now + 5_000, now)).toBe('last update 0 s ago');
  });
});
