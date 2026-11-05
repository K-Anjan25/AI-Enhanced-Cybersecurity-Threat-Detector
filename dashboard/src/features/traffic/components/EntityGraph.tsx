/** A bounded, technical list of observed directed source → destination flows. */
import { EmptyState } from '../../../components/ui';
import { formatBytes, formatCount } from '../../../lib/format';
import type { GraphModel } from '../graph';

export interface EntityGraphProps {
  model: GraphModel;
  /** The pinned address, or `null`. */
  pinnedId: string | null;
  onPin: (id: string | null) => void;
}

function EndpointButton({
  address,
  direction,
  pinnedId,
  onPin,
}: {
  address: string;
  direction: 'source' | 'destination';
  pinnedId: string | null;
  onPin: (id: string | null) => void;
}) {
  const selected = pinnedId === address;
  const action = selected ? 'Unpin' : 'Pin';
  return (
    <button
      type="button"
      className={`rounded-input px-1 py-0.5 text-left font-mono text-body-sm underline-offset-2 hover:text-accent hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent ${selected ? 'bg-surface text-accent' : 'text-ink'}`}
      aria-label={`${action} ${direction} endpoint ${address}`}
      aria-pressed={selected}
      onClick={() => onPin(selected ? null : address)}
    >
      {address}
    </button>
  );
}

/** Render the highest-volume relationships without force layout or quadratic work. */
export function EntityGraph({ model, pinnedId, onPin }: EntityGraphProps) {
  if (model.addressCount === 0) {
    return <EmptyState title="No addresses in this selection" />;
  }

  if (model.totalRelationships === 0) {
    return (
      <p role="status" className="py-4 text-body-sm text-muted">
        No flow relationships between the visible addresses.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-body-sm text-muted">
        Showing {formatCount(model.relationships.length)} of {formatCount(model.totalRelationships)}{' '}
        directed conversations between visible addresses, ranked by observed bytes. Pin either
        endpoint to focus the address table.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <caption className="sr-only">
            Directed source-to-destination conversations with observed flow and byte counts.
          </caption>
          <thead>
            <tr className="border-b border-line font-mono text-caption text-muted">
              <th scope="col" className="px-2 py-2 font-semibold">
                SOURCE
              </th>
              <th scope="col" className="px-2 py-2 font-semibold">
                DESTINATION
              </th>
              <th scope="col" className="px-2 py-2 text-right font-semibold">
                FLOWS
              </th>
              <th scope="col" className="px-2 py-2 text-right font-semibold">
                OBSERVED BYTES
              </th>
            </tr>
          </thead>
          <tbody>
            {model.relationships.map((relationship, index) => (
              <tr
                key={`${relationship.source}->${relationship.target}`}
                data-testid={`relationship-${index}`}
                className="border-b border-line/60 last:border-b-0"
              >
                <td className="whitespace-nowrap px-2 py-2">
                  <EndpointButton
                    address={relationship.source}
                    direction="source"
                    pinnedId={pinnedId}
                    onPin={onPin}
                  />
                </td>
                <td className="whitespace-nowrap px-2 py-2">
                  <span aria-hidden="true" className="mr-2 text-muted">
                    →
                  </span>
                  <EndpointButton
                    address={relationship.target}
                    direction="destination"
                    pinnedId={pinnedId}
                    onPin={onPin}
                  />
                </td>
                <td className="whitespace-nowrap px-2 py-2 text-right font-mono text-body-sm text-ink">
                  {formatCount(relationship.flows)}
                </td>
                <td className="whitespace-nowrap px-2 py-2 text-right font-mono text-body-sm text-ink">
                  {formatBytes(relationship.bytes)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pinnedId === null ? null : (
        <p className="text-body-sm text-muted">
          Pinned endpoint: <code className="text-accent">{pinnedId}</code>
        </p>
      )}
    </div>
  );
}
