/**
 * Packet-capture control (step 4): what the sensor should be running.
 *
 * The API stores the desired state; the capture container reads it and reconciles to
 * it within a few seconds. Starting here does not start a container, so the wire
 * shape says "desired", and the panel says the same thing to the operator.
 */
import { getJson, putJson } from './client';

export const CAPTURE_STATE_PATH = '/api/v1/capture/state';

export interface CaptureState {
  running: boolean;
  engines: string[];
  version: number;
  changed_by: string | null;
  changed_at: string | null;
}

export interface CaptureStateChange {
  running: boolean;
  engines: string[];
}

export async function fetchCaptureState(signal?: AbortSignal): Promise<CaptureState> {
  return getJson<CaptureState>(CAPTURE_STATE_PATH, { signal });
}

export async function setCaptureState(change: CaptureStateChange): Promise<CaptureState> {
  return putJson<CaptureState>(CAPTURE_STATE_PATH, change);
}
