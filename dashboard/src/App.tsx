/**
 * Route table (design.md §3 information architecture).
 *
 * Overview (T-403, §4.1), Alert triage (T-404, §4.3), Traffic (T-406, §4.4), Logs
 * (T-407, §4.5) and Hunt (T-408, §4.6) exist. Every other route renders an explicit
 * "not built" state rather than a blank panel or a dead link, so the navigation
 * reflects reality (design.md §8.1).
 *
 * The toast provider is mounted here rather than at the entry point because it is
 * part of the app's own tree: a route that reports the result of an action (the
 * hunt's export, T-408) has to have somewhere to report it in every environment the
 * app is rendered in, tests included. It renders an empty notifications region
 * until something is raised, so mounting it costs a screen nothing.
 */
import { Route, Routes } from 'react-router-dom';

import { AppShell } from './components/layout/AppShell';
import { ToastProvider } from './components/ui';
import { HuntPage } from './features/hunt/pages/HuntPage';
import { LogsPage } from './features/logs/pages/LogsPage';
import { OverviewPage } from './features/overview/pages/OverviewPage';
import { TrafficPage } from './features/traffic/pages/TrafficPage';
import { TriagePage } from './features/triage/pages/TriagePage';

const PENDING: Record<string, string> = {
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
    <ToastProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<OverviewPage />} />
          <Route path="/alerts" element={<TriagePage />} />
          <Route path="/alerts/:alertId" element={<TriagePage />} />
          <Route path="/traffic" element={<TrafficPage />} />
          <Route path="/logs" element={<LogsPage />} />
          <Route path="/hunt" element={<HuntPage />} />
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
    </ToastProvider>
  );
}
