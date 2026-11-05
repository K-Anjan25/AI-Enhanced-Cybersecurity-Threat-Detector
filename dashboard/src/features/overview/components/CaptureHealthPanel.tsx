/** A truthful view of the Docker capture service's backend-received heartbeats. */
import { Badge } from '../../../components/ui';
import type { CaptureHealth } from '../api';

interface CaptureHealthPanelProps {
  health: CaptureHealth | undefined;
  loading: boolean;
  error: boolean;
}

function ageLabel(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} seconds ago`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'} ago`;
}

function statusLabel(status: CaptureHealth['status']): string {
  if (status === 'healthy') return 'Healthy';
  if (status === 'stale') return 'Stale';
  return 'Unknown';
}

function statusTone(status: CaptureHealth['status']): 'benign' | 'critical' | 'neutral' {
  if (status === 'healthy') return 'benign';
  return status === 'stale' ? 'critical' : 'neutral';
}

export function CaptureHealthPanel({ health, loading, error }: CaptureHealthPanelProps) {
  return (
    <section
      aria-labelledby="capture-health-title"
      className="rounded-card border border-line bg-surface p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="capture-health-title" className="text-h2">
          Capture sensor health
        </h2>
        {health === undefined ? null : (
          <Badge tone={statusTone(health.status)}>{statusLabel(health.status)}</Badge>
        )}
      </div>
      <p className="mt-2 text-body-sm text-muted">
        Source: authenticated heartbeats received by the backend from the Docker capture service.
        This is sensor liveness, not an estimate of traffic volume.
      </p>

      {health === undefined && loading ? (
        <p role="status" className="mt-3 text-body-sm text-muted">
          Checking capture sensor heartbeats…
        </p>
      ) : health === undefined && error ? (
        <p role="status" className="mt-3 text-body-sm text-muted">
          Capture status could not be read from the backend.
        </p>
      ) : health === undefined ? (
        <p className="mt-3 text-body-sm text-muted">Capture status is not available yet.</p>
      ) : health.sensors.length === 0 ? (
        <p className="mt-3 text-body-sm text-muted">
          No capture sensor has reported. Status is unknown, not evidence that no traffic exists.
        </p>
      ) : (
        <ul className="mt-3 flex flex-col gap-3">
          {health.sensors.map((sensor) => (
            <li
              key={sensor.sensor_id}
              className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3"
            >
              <div className="min-w-0">
                <p className="break-all font-mono text-body-sm font-semibold text-ink">
                  {sensor.sensor_id}
                </p>
                <p className="mt-1 text-caption text-muted">Engines: {sensor.engines.join(', ')}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={sensor.status === 'healthy' ? 'benign' : 'critical'}>
                  {statusLabel(sensor.status)}
                </Badge>
                <time
                  dateTime={sensor.last_seen_at}
                  title={`Server received ${sensor.last_seen_at}`}
                  className="font-mono text-caption tabular-nums text-muted"
                >
                  {ageLabel(sensor.age_seconds)}
                </time>
              </div>
            </li>
          ))}
        </ul>
      )}

      {health === undefined || health.sensors.length === 0 ? null : (
        <p className="mt-3 text-caption text-muted">
          A sensor is stale after {health.heartbeat_timeout_seconds} seconds without a heartbeat.
        </p>
      )}
    </section>
  );
}
