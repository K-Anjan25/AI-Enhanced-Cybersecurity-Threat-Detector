import React from "react";
import ReactDOM from "react-dom/client";
import { MotionConfig } from "framer-motion";
import { Provider } from "react-redux";
import { QueryClient, QueryClientProvider } from "react-query";
import store from "./store/store";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ToastProvider } from "./utils/toastBridge";
import { ThemeProvider } from "./theme/ThemeProvider";
import "@fontsource-variable/dm-sans";
import "@fontsource/space-mono/400.css";
import "@fontsource/space-mono/700.css";
import "./index.css";

// 1. Create a QueryClient instance
const queryClient = new QueryClient();

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Failed to find the root element");
}

const root = ReactDOM.createRoot(rootElement);

root.render(
  <React.StrictMode>
    <Provider store={store}>
      {/* 2. Wrap App inside QueryClientProvider */}
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <ErrorBoundary>
            <ThemeProvider>
              {/* Motion contract (spec §40.8): framer-motion animates with
                  JS, so the global CSS reduced-motion override in globals.css
                  does not reach it. `reducedMotion="user"` makes every motion
                  component honour the OS setting — transforms are dropped,
                  opacity/color still animate. */}
              <MotionConfig reducedMotion="user">
                <App />
              </MotionConfig>
            </ThemeProvider>
          </ErrorBoundary>
        </ToastProvider>
      </QueryClientProvider>
    </Provider>
  </React.StrictMode>
);