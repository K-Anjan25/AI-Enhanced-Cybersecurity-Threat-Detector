/**
 * Route table (design.md §3 information architecture).
 *
 * Every screen design.md §3 names now exists: Overview (T-403, §4.1), Alert triage
 * (T-404, §4.3), Traffic (T-406, §4.4), Logs (T-407, §4.5), Hunt (T-408, §4.6), Model
 * ops with its drift page (T-409, §4.7) and Admin with its six sections (T-410,
 * T-422, §4.8). `/admin/connectors` was the last one, and T-422 built it, so the
 * router no longer carries a "not built" state at all: a path outside the design's
 * tree is a 404, and a path inside it is a screen.
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
 *
 * **Below 768 px the public screens are not the routes but notices** (T-412,
 * design.md §8.3). `Offered` wraps every screen except triage: when the viewport
 * class is `narrow` it renders an empty state instead of mounting the page, so a
 * phone does not fetch a dashboard nobody can read — the panels are absent rather
 * than merely hidden, which is also what makes the refusal testable by request count.
 * `/alerts` and `/alerts/:alertId` are the loop §8.3 keeps, so they are not wrapped.
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Route, Routes } from 'react-router-dom';

import { sessionToken, onSessionTokenChange } from './api/session';
import { signOut } from './api/auth';
import { AppShell } from './components/layout/AppShell';
import { EmptyState } from './components/ui';
import { useViewportClass } from './components/hooks/viewport';
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
import { SignInPage } from './features/auth/SignInPage';

/**
 * A screen, when the window is wide enough for it to be offered (§8.3).
 *
 * The notice is not a banner: the shell already renders §8.3's banner, and two
 * sentences saying the same thing a line apart is how a reader learns to skip both.
 * This is the page — it says which screen is missing and what is here instead.
 */
function Offered({ children }: { children: ReactNode }) {
  const viewport = useViewportClass();
  if (viewport !== 'narrow') return <>{children}</>;
  return (
    <div className="max-w-xl">
      <h1 className="text-h1">Not offered at this window size</h1>
      <EmptyState
        title="This screen needs a wider window"
        description="Below 768 px the console is the triage loop: the alert list and the alert detail. Widen the window, or rotate the device, to bring the rest back."
      />
    </div>
  );
}

/**
 * The routes, plus the shell — inside the provider, because the top bar's search
 * control opens the palette and so needs the handle the provider publishes.
 */
function Shell({ onSignOut }: { onSignOut: () => void }) {
  const { openPalette } = useCommands();
  return (
    <Routes>
      <Route element={<AppShell onOpenPalette={openPalette} onSignOut={onSignOut} />}>
        <Route
          index
          element={
            <Offered>
              <OverviewPage />
            </Offered>
          }
        />
        <Route path="/alerts" element={<TriagePage />} />
        <Route path="/alerts/:alertId" element={<TriagePage />} />
        <Route
          path="/traffic"
          element={
            <Offered>
              <TrafficPage />
            </Offered>
          }
        />
        <Route
          path="/logs"
          element={
            <Offered>
              <LogsPage />
            </Offered>
          }
        />
        <Route
          path="/hunt"
          element={
            <Offered>
              <HuntPage />
            </Offered>
          }
        />
        <Route
          path="/models"
          element={
            <Offered>
              <ModelsPage />
            </Offered>
          }
        />
        <Route
          path="/models/drift"
          element={
            <Offered>
              <DriftPage />
            </Offered>
          }
        />
        {/* One route for `/admin` and its children: the section nav is inside the
              page, and the child paths match relative to it. */}
        <Route
          path="/admin/*"
          element={
            <Offered>
              <AdminPage />
            </Offered>
          }
        />
        <Route
          path="*"
          element={
            <Offered>
              <div>
                <h1 className="text-h1">Page not found</h1>
                <p className="mt-2 text-body text-muted">
                  No route matches this address. Check the navigation for available screens.
                </p>
              </div>
            </Offered>
          }
        />
      </Route>
    </Routes>
  );
}

export function App() {
  const [token, setToken] = useState(() => sessionToken());
  useEffect(() => onSessionTokenChange(setToken), []);
  const handleSignOut = useCallback(() => {
    void signOut().catch(() => undefined);
  }, []);

  if (token === null) return <SignInPage />;

  return (
    <ToastProvider>
      <CommandProvider
        // Read on the open edge: the palette offers whatever this browser has saved
        // by the time it is asked, not what was saved when the app started.
        listSavedHunts={() => savedHunts(huntStoreSubject(sessionToken()))}
      >
        <Shell onSignOut={handleSignOut} />
      </CommandProvider>
    </ToastProvider>
  );
}
