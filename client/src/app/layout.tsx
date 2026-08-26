import "./globals.css";
import { Metadata } from "next";
import { ReactNode } from "react";
import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Provider as ReduxProvider } from "react-redux";
import store from "../store/store";
import ErrorBoundary from "@/components/ErrorBoundary";
import { ToastProvider } from "@/utils/toastBridge";
import { ThemeToggle } from "@/components/layout/ThemeToggle";

const queryClient = new QueryClient();

export function metadata(): Metadata {
  return {
    title: "NOCTRA — Cybersecurity Threat Detector",
    description: "AI-native SOC platform: detects across logs, email and network, explains every verdict, and orchestrates response.",
    themeColor: "#0f0f0f",
  };
}

export default function RootLayout({
  children,
}: { children: ReactNode }) {
  const [theme, setTheme] = useState("light");
  useEffect(() => {
    // Read prefers-color-scheme on mount
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    setTheme(mq.matches ? "dark" : "light");
    mq.addEventListener("change", (e) => setTheme(e.matches ? "dark" : "light"));
  }, []);

  return (
    <html lang="en" suppressHydrationWarning={true}>
      <body className="bg-background text-foreground antialiased">
        <ThemeToggle initial={theme} />
        <ReduxProvider store={store}>
          <ErrorBoundary>
            <QueryClientProvider client={queryClient}>
              {children}
            </QueryClientProvider>
          </ErrorBoundary>
        </ReduxProvider>
      </body>
    </html>
  );
}