/**
 * Overview page — Sprint S0 state.
 *
 * The real dashboard is T-403. Rather than rendering empty panels that look like
 * working widgets (design.md §8.1: never render a blank panel where data failed
 * to arrive), this page states plainly what exists and what does not.
 */
const S0_STATUS = [
  { label: 'Ingest API', detail: 'skeleton — /healthz, /readyz', state: 'partial' },
  { label: 'Model service', detail: 'skeleton — no model loaded', state: 'partial' },
  { label: 'Flow model (FlowNet)', detail: 'not started — T-201', state: 'missing' },
  { label: 'Log model (LogNet)', detail: 'not started — T-204', state: 'missing' },
  { label: 'Alert pipeline', detail: 'not started — T-308', state: 'missing' },
] as const;

export function OverviewPage() {
  return (
    <div className="max-w-2xl">
      <h1 className="text-h1">Overview</h1>
      <p className="mt-2 text-body text-muted">
        No telemetry is being analysed yet. This is the Sprint S0 skeleton: the shell, routing,
        theming, and design tokens are in place, and the detection pipeline is not.
      </p>

      <table className="mt-6 w-full border-collapse text-body-sm">
        <caption className="sr-only">Current build status of each pipeline stage</caption>
        <thead>
          <tr className="border-b border-line text-left">
            <th scope="col" className="py-2 pr-4 font-semibold">
              Component
            </th>
            <th scope="col" className="py-2 font-semibold">
              Status
            </th>
          </tr>
        </thead>
        <tbody>
          {S0_STATUS.map((row) => (
            <tr key={row.label} className="border-b border-line">
              <th scope="row" className="py-2 pr-4 text-left font-normal">
                {row.label}
              </th>
              <td className="py-2 text-muted">{row.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="mt-6 text-caption text-muted">
        Targets and acceptance criteria live in <code className="font-mono">prd.md</code> and{' '}
        <code className="font-mono">task.md</code>.
      </p>
    </div>
  );
}
