/**
 * Route table (design.md §3 information architecture).
 *
 * Overview (T-403, §4.1), Alert triage (T-404, §4.3), Traffic (T-406, §4.4), Logs
 * (T-407, §4.5), Hunt (T-408, §4.6), Model ops with its drift page (T-409, §4.7) and
 * Admin (T-410, §4.8) exist. Every other route renders an explicit "not built" state
 * rather than a blank panel or a dead link, so the navigation reflects reality
 * (design.md §8.1) — `/admin/connectors` is the one left, and it names T-422, the task
 * that will build it, because design.md §3 gives it a route and the backlog had no row
 * for the screen.
 *
 * The toast provider is mounted here rather than at the entry point because it is
 * part of the app's own tree: a route that reports the result of an action (the
 * hunt's export, T-408) has to have somewhere to report it in every environment the
 * app is rendered in, tests included. It renders an empty notifications region
 * until something is raised, so mounting it costs a screen nothing.
 *
 * The command palette (T-411) is wired here too, and for the same compositional
 * reason: it navigates every route and runs the hunt console's saved queries, and
 * those two sources live on opposite sides of the feature boundary. This is the only
 * layer allowed to read both, so this is where the provider is mounted and where the
 * saved hunts are handed in as a function.
 */
import { Route, Routes } from 'react-router-dom';

import { sessionToken } from './api/session';
import { AppShell } from './components/layout/AppShell';
import { ToastProvider } from './components/ui';
import { CommandProvider, useCommands } from './features/command/provider';
import { huntStoreSubject, savedHunts } from './features/hunt/saved';
import { AdminPage } from './features/admin/pages/AdminPage';
import { HuntPage } from './features/hunt/pages/HuntPage';
import { LogsPage } from './features/logs/pages/LogsPage';
import { DriftPage } from './features/models/pages/DriftPage';
import { ModelsPage } from './features/models/pages/ModelsPage';
import { OverviewPage } from './features/overview/pages/OverviewPage';
import { TrafficPage } from './features/traffic/pages/TrafficPage';
import { TriagePage } from './features/triage/pages/TriagePage';

const PENDING: Record<string, string> = {
  '/admin/connectors': 'T-422',
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

/**
 * The routes, plus the shell — inside the provider, because the top bar's search
 * control opens the palette and so needs the handle the provider publishes.
 */
function Shell() {
  const { openPalette } = useCommands();
  return (
    <Routes>
      <Route element={<AppShell onOpenPalette={openPalette} />}>
        <Route index element={<OverviewPage />} />
        <Route path="/alerts" element={<TriagePage />} />
        <Route path="/alerts/:alertId" element={<TriagePage />} />
        <Route path="/traffic" element={<TrafficPage />} />
        <Route path="/logs" element={<LogsPage />} />
        <Route path="/hunt" element={<HuntPage />} />
        <Route path="/models" element={<ModelsPage />} />
        <Route path="/models/drift" element={<DriftPage />} />
        {/* One route for `/admin` and its children: the section nav is inside the
              page, and the child paths match relative to it. */}
        <Route path="/admin/*" element={<AdminPage />} />
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

export function App() {
  return (
    <ToastProvider>
      <CommandProvider
        // Read on the open edge: the palette offers whatever this browser has saved
        // by the time it is asked, not what was saved when the app started.
        listSavedHunts={() => savedHunts(huntStoreSubject(sessionToken()))}
      >
        <Shell />
      </CommandProvider>
    </ToastProvider>
  );
}
