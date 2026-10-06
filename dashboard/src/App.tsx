/**
 * Route table (design.md §3 information architecture).
 *
 * Overview (T-403, §4.1), Alert triage (T-404, §4.3), Traffic (T-406, §4.4) and Logs
 * (T-407, §4.5) exist. Every other route renders an explicit "not built" state rather
 * than a blank panel or a dead link, so the navigation reflects reality
 * (design.md §8.1).
 */
import { Route, Routes } from 'react-router-dom';

import { AppShell } from './components/layout/AppShell';
import { LogsPage } from './features/logs/pages/LogsPage';
import { OverviewPage } from './features/overview/pages/OverviewPage';
import { TrafficPage } from './features/traffic/pages/TrafficPage';
import { TriagePage } from './features/triage/pages/TriagePage';

const PENDING: Record<string, string> = {
  '/hunt': 'T-408',
  '/models': 'T-409',
  '/admin': 'T-410',
};

function NotYetBuilt({ path }: { path: string }) {
  const task = PENDING[path] ?? 'unplanned';
  return (
    <div className="max-w-xl">
      <h1 className="text-h1">Not built yet</h1>
      <p className="mt-2 text-body text-muted">
        This screen is scheduled as task <code className="font-mono">{task}</code> in{' '}
        <code className="font-mono">task.md</code>. The route exists so navigation is honest about
        what the build currently covers.
      </p>
    </div>
  );
}

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="/alerts" element={<TriagePage />} />
        <Route path="/alerts/:alertId" element={<TriagePage />} />
        <Route path="/traffic" element={<TrafficPage />} />
        <Route path="/logs" element={<LogsPage />} />
        {Object.keys(PENDING).map((path) => (
          <Route key={path} path={path} element={<NotYetBuilt path={path} />} />
        ))}
        <Route
          path="*"
          element={
            <div>
              <h1 className="text-h1">Page not found</h1>
              <p className="mt-2 text-body text-muted">
                No route matches this address. Check the navigation for available screens.
              </p>
            </div>
          }
        />
      </Route>
    </Routes>
  );
}
