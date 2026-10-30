/**
 * Packet capture control (step 4). The operator asks for capture to run, or to stop,
 * and chooses the engines. The sensor applies the request; this panel shows what was
 * asked for and when, and never claims the sensor has already applied it.
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { fetchCaptureState, setCaptureState, type CaptureState } from '../../../api/capture';
import { Badge, Button, Card } from '../../../components/ui';
import {
  CAPTURE_ENGINES,
  CAPTURE_SCOPE_NOTE,
  canStart,
  describeRequest,
  orderEngines,
  toggleEngine,
} from '../capture';

export function CapturePanel() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ['admin', 'capture'],
    queryFn: ({ signal }) => fetchCaptureState(signal),
  });
  const change = useMutation({
    mutationFn: setCaptureState,
    onSuccess: (state: CaptureState) => {
      client.setQueryData(['admin', 'capture'], state);
      void client.invalidateQueries({ queryKey: ['admin', 'audit'] });
    },
  });

  const state = query.data;
  // Local selection until the operator changes it; the server's engines otherwise.
  const [picked, setPicked] = useState<string[] | null>(null);
  const selected = picked ?? (state ? orderEngines(state.engines) : []);

  if (query.isError) {
    return <Card title="Packet capture">Capture state could not be read: {query.error.message}</Card>;
  }

  const request = (running: boolean) => {
    change.mutate({ running, engines: orderEngines(selected) });
    setPicked(null);
  };

  return (
    <Card title="Packet capture">
      <p>
        <Badge tone={state?.running ? 'info' : 'neutral'}>{state?.running ? 'Requested' : 'Stopped'}</Badge>{' '}
        {state ? describeRequest(state) : 'Loading…'}
      </p>
      {state?.changed_by && state.changed_at ? (
        <p>
          Last changed by {state.changed_by} at {new Date(state.changed_at).toLocaleString()} (version{' '}
          {state.version}).
        </p>
      ) : null}

      <fieldset>
        <legend>Engines</legend>
        {CAPTURE_ENGINES.map((engine) => (
          <label key={engine.id} style={{ display: 'block' }}>
            <input
              type="checkbox"
              checked={selected.includes(engine.id)}
              onChange={() => setPicked(toggleEngine(selected, engine.id))}
            />{' '}
            <strong>{engine.label}</strong> <span>{engine.note}</span>
          </label>
        ))}
      </fieldset>

      <p>
        <Button onClick={() => request(true)} disabled={!canStart(selected) || change.isPending}>
          Start capture
        </Button>{' '}
        <Button variant="secondary" onClick={() => request(false)} disabled={change.isPending}>
          Stop capture
        </Button>
      </p>
      {change.isError ? <p role="alert">Change not saved: {change.error.message}</p> : null}
      <p>{CAPTURE_SCOPE_NOTE}</p>
    </Card>
  );
}
