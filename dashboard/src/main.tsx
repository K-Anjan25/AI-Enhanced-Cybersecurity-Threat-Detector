/**
 * Application entry point.
 *
 * One QueryClient for all server state (rule R-24), one router, and one realtime
 * connection for the whole app (T-405, architecture.md §10). Server state never
 * lives in useState or the global store.
 *
 * The realtime provider sits *inside* the query client, because its consumers
 * re-read queries when alerts arrive (`useAlertSync`) — a provider above the cache
 * could not do that — and outside the router, because the connection outlives any
 * one route.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import { App } from './App';
import { RealtimeProvider } from './components/realtime/RealtimeProvider';
import './index.css';
import { ThemeProvider } from './theme/ThemeProvider';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 5_000,
    },
  },
});

const container = document.getElementById('root');
if (container === null) {
  throw new Error('Root container #root is missing from index.html');
}

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RealtimeProvider>
        <ThemeProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ThemeProvider>
      </RealtimeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
