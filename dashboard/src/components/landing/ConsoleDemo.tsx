import React, { useState } from "react";
import { Radar } from "lucide-react";
import { buttonVariants } from "../ui/Button";
import { cn } from "../ui/Button";

/**
 * ConsoleDemo — the interactive console preview (#console), ported 1:1 from
 * newfile.html: console panel with live status header, metric cards,
 * prioritized event rows (threat-items) and the scan radar aside whose
 * is-scanning state drives the sweep/ring/core animations.
 */
const METRICS = [
  { label: "Assets mapped", value: "1,284" },
  { label: "Signals / hour", value: "48.7k" },
  { label: "Critical paths", value: "03" },
  { label: "Noise reduced", value: "92%" },
] as const;

const EVENTS = [
  {
    title: "Unusual privileged access sequence",
    meta: "Identity surface · 2 endpoints",
    tag: "Investigate",
  },
  {
    title: "External service fingerprint changed",
    meta: "Perimeter surface · 1 asset",
    tag: "Review",
  },
] as const;

const ConsoleDemo: React.FC = () => {
  const [scanning, setScanning] = useState(false);

  return (
    <section id="console" className="mx-auto max-w-7xl scroll-mt-16 px-5 py-20 lg:px-8 lg:py-28">
      <div className="mb-10 max-w-2xl">
        <p className="tech-label text-accent-primary">The NOCTRA console</p>
        <h2 className="mt-4 text-display-lg font-bold text-content-primary">
          Security telemetry, made operational.
        </h2>
        <p className="mt-4 leading-7 text-content-secondary">
          Move from raw events to a clear, continuously updated security narrative. This
          interactive preview shows how NOCTRA keeps your team focused.
        </p>
      </div>

      <div
        id="dashboard-demo"
        className={cn("console-panel overflow-hidden rounded-sm", scanning && "is-scanning")}
      >
        {/* Panel header — live status */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="signal-dot" aria-hidden="true" />
            <p className="tech-label text-content-primary">NOCTRA / command center</p>
          </div>
          <p className="tech-label rounded-full border border-accent-primary/30 bg-accent-primary/10 px-3 py-1 text-accent-primary">
            Systems nominal
          </p>
        </div>

        <div className="grid gap-4 p-5 lg:grid-cols-[1.2fr_.8fr]">
          {/* Threat overview */}
          <section aria-label="Threat overview">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {METRICS.map((m) => (
                <div key={m.label} className="border border-line-subtle bg-app-void/55 p-4 rounded-sm">
                  <p className="tech-label text-content-tertiary">{m.label}</p>
                  <p className="mt-3 text-2xl font-bold tabular-nums tracking-tight text-content-primary">
                    {m.value}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-4 rounded-sm border border-line-subtle bg-app-void/50 p-5">
              <div className="flex items-center justify-between gap-4">
                <p className="tech-label text-content-primary">Prioritized events</p>
                <p className="tech-label text-content-tertiary">Last 15 minutes</p>
              </div>
              <div className="mt-4 space-y-3">
                {EVENTS.map((e) => (
                  <div
                    key={e.title}
                    className="threat-item flex items-center justify-between gap-3 rounded-sm px-4 py-3"
                  >
                    <div>
                      <p className="text-sm font-semibold text-content-primary">{e.title}</p>
                      <p className="tech-label mt-1.5 text-content-tertiary">{e.meta}</p>
                    </div>
                    <span className="tech-label whitespace-nowrap text-accent-primary">{e.tag}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Scan controls — the interactive radar */}
          <aside className="rounded-sm border border-line-subtle bg-app-void/50 p-5" aria-label="Scan controls">
            <div className="flex items-start justify-between">
              <div>
                <p className="tech-label text-content-tertiary">Autonomous scanning</p>
                <p className="mt-2 font-bold text-content-primary">Continuous signal sweep</p>
              </div>
              <Radar className="h-5 w-5 text-accent-primary" aria-hidden="true" />
            </div>

            <div className="relative mt-8 grid min-h-40 place-items-center overflow-hidden rounded-sm border border-accent-primary/15 bg-app-void">
              <div className="scan-line absolute inset-y-0 w-1/2" aria-hidden="true" />
              <div className="scan-ring">
                <span className="scan-core" />
              </div>
            </div>

            <div className="mt-5">
              <p
                className={cn(
                  "text-sm leading-6 text-content-secondary",
                  scanning && "hidden"
                )}
              >
                The sweep runs continuously across your environment. Start a scan to watch
                NOCTRA triage signals in real time.
              </p>
              <p
                className={cn(
                  "text-sm leading-6 text-content-secondary",
                  !scanning && "hidden"
                )}
              >
                Scanning — correlating weak signals into evidence-backed priorities and
                ranking what deserves your attention first.
              </p>
            </div>

            <button
              type="button"
              onClick={() => setScanning(true)}
              className={cn(
                buttonVariants({ variant: "primary", size: "lg" }),
                "mt-6 w-full",
                scanning && "hidden"
              )}
            >
              Start scan
            </button>
            <button
              type="button"
              onClick={() => setScanning(false)}
              className={cn(
                buttonVariants({ variant: "secondary", size: "lg" }),
                "mt-6 w-full",
                !scanning && "hidden"
              )}
            >
              Reset scan
            </button>
          </aside>
        </div>
      </div>
    </section>
  );
};

export default ConsoleDemo;
