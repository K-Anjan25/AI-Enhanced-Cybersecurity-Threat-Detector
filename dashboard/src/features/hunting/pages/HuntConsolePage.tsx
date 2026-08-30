import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Bookmark, Play, Search } from "lucide-react";
import apiClient from "../../../api/client";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Modal,
  PageHeader,
  SeverityBadge,
  SkeletonCard,
} from "../../../components/ui";
import { useToast } from "../../../components/ui/Toast";
import { getApiError } from "../../../utils/getApiError";

/**
 * Threat hunting — ask a question of the alert history and get an answer.
 *
 * Hunts could be written and listed but never run from the dashboard, so the
 * feature was a notebook with no execute button. This is the console: type a
 * query, see the matching alerts, save the useful ones.
 *
 * The honesty rule that matters here is specific to search. An analyst reads
 * "no results" as "nothing to find", so a query that was misunderstood is more
 * dangerous than one that fails. Every response says what the backend did with
 * it: fields it did not recognise, conditions it could not apply, and whether
 * the result set was cut short by the row limit.
 */

interface HuntRow {
  id: number;
  severity: string;
  source: string;
  source_ip: string | null;
  message: string;
  alert_type: string | null;
  mitre_technique_id: string | null;
  created_at: string | null;
}

interface HuntResult {
  query: string;
  result_count: number;
  results: HuntRow[];
  duration_ms: number;
  truncated: boolean;
  limit: number;
  unknown_fields: string[];
  unsupported: string[];
  honest_note: string;
}

interface SavedHunt {
  id: number;
  name: string;
  query: string;
  description: string | null;
  is_saved: boolean;
}

const asList = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);

const EXAMPLES = [
  "severity:CRITICAL",
  "severity:CRITICAL OR severity:HIGH",
  "source:okta AND NOT severity:LOW",
  "source_ip:203.0.113.9",
];

export default function HuntConsolePage() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<HuntResult | null>(null);
  const [running, setRunning] = useState(false);
  const [saved, setSaved] = useState<SavedHunt[]>([]);
  const [loadingSaved, setLoadingSaved] = useState(true);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const { push } = useToast();

  const loadSaved = useCallback(async () => {
    setLoadingSaved(true);
    try {
      const res = await apiClient.get("/hunts");
      setSaved(asList<SavedHunt>(res.data));
    } catch (e) {
      push(getApiError(e, "Could not load saved hunts"), "error");
    } finally {
      setLoadingSaved(false);
    }
  }, [push]);

  useEffect(() => {
    void loadSaved();
  }, [loadSaved]);

  const run = async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) return;
    setRunning(true);
    try {
      const res = await apiClient.post("/hunts/execute", { query: trimmed });
      setResult(res.data as HuntResult);
    } catch (e) {
      // A failed hunt must not leave the previous results on screen looking
      // like the answer to the new question.
      setResult(null);
      push(getApiError(e, "The hunt could not be run"), "error");
    } finally {
      setRunning(false);
    }
  };

  const save = async () => {
    const name = saveName.trim();
    if (!name || !query.trim()) return;
    try {
      await apiClient.post("/hunts", { name, query: query.trim(), is_saved: true });
      push(`Saved "${name}"`);
      setSaveOpen(false);
      setSaveName("");
      await loadSaved();
    } catch (e) {
      push(getApiError(e, "Could not save the hunt"), "error");
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Threat hunting"
        description="Ask a question of your alert history. Results come from your tenant's recorded alerts only."
      />

      <Card className="p-5 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-[260px]">
            <Search
              size={14}
              aria-hidden
              className="absolute left-3 top-1/2 -translate-y-1/2 text-content-tertiary"
            />
            <input
              aria-label="Hunt query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void run(query);
              }}
              placeholder="severity:CRITICAL AND source:okta"
              className="w-full bg-app-subtle border border-line-subtle rounded-sm pl-9 pr-3 py-2 text-sm font-mono text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary"
            />
          </div>
          <Button size="sm" onClick={() => void run(query)} disabled={running || !query.trim()}>
            <Play size={13} className="mr-1.5" /> {running ? "Running…" : "Run"}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setSaveOpen(true)}
            disabled={!query.trim()}
          >
            <Bookmark size={13} className="mr-1.5" /> Save
          </Button>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[11px] text-content-tertiary">Try:</span>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => {
                setQuery(example);
                void run(example);
              }}
              className="text-[11px] font-mono px-2 py-1 rounded-sm bg-app-subtle border border-line-subtle text-content-secondary hover:border-accent-primary"
            >
              {example}
            </button>
          ))}
        </div>
      </Card>

      {running ? (
        <SkeletonCard />
      ) : result ? (
        <>
          {/* What the backend did with the query, before the results. */}
          {(result.unknown_fields.length > 0 || result.unsupported.length > 0 || result.truncated) && (
            <Card className="p-4 border-status-warning/40">
              <div className="flex items-start gap-2">
                <AlertTriangle
                  size={15}
                  className="text-status-warning shrink-0 mt-0.5"
                  aria-hidden
                />
                <div className="text-xs text-content-secondary space-y-1">
                  {result.unknown_fields.length > 0 && (
                    <p>
                      <span className="font-medium text-content-primary">
                        Unrecognised field{result.unknown_fields.length === 1 ? "" : "s"}:
                      </span>{" "}
                      <span className="font-mono">{result.unknown_fields.join(", ")}</span> —
                      searched the message text instead. Check the spelling if this is not
                      what you meant.
                    </p>
                  )}
                  {result.unsupported.length > 0 && (
                    <p>
                      <span className="font-medium text-content-primary">Ignored:</span>{" "}
                      <span className="font-mono">{result.unsupported.join(", ")}</span> —
                      this condition could not be applied, so the results are broader than
                      you asked for.
                    </p>
                  )}
                  {result.truncated && (
                    <p>
                      <span className="font-medium text-content-primary">
                        Showing the first {result.limit}.
                      </span>{" "}
                      There may be more matches — narrow the query to see the rest.
                    </p>
                  )}
                </div>
              </div>
            </Card>
          )}

          <Card className="p-5">
            <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
              <h2 className="text-sm font-bold font-display text-content-primary">
                {result.result_count} match{result.result_count === 1 ? "" : "es"}
              </h2>
              <span className="text-[11px] text-content-tertiary tabular-nums">
                {result.duration_ms} ms
              </span>
            </div>

            {result.result_count === 0 ? (
              <p className="text-xs text-content-secondary">
                No alert matches this query. That is a real answer — the query ran and your
                tenant has nothing matching it.
              </p>
            ) : (
              <div className="space-y-2">
                {result.results.map((row) => (
                  <div
                    key={row.id}
                    className="flex items-start justify-between gap-3 flex-wrap border-b border-line-subtle last:border-0 pb-2 last:pb-0"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <SeverityBadge severity={row.severity} />
                        <span className="text-xs text-content-secondary">{row.source}</span>
                        {row.source_ip && (
                          <span className="text-xs font-mono text-content-tertiary">
                            {row.source_ip}
                          </span>
                        )}
                        {row.mitre_technique_id && (
                          <Badge className="bg-app-subtle text-content-tertiary border-line-subtle">
                            {row.mitre_technique_id}
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-content-primary mt-1">{row.message}</p>
                    </div>
                    <span className="text-[11px] text-content-tertiary shrink-0">
                      {row.created_at ? new Date(row.created_at).toLocaleString() : ""}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      ) : null}

      <Card className="p-5">
        <h2 className="text-sm font-bold font-display text-content-primary mb-3">
          Saved hunts
        </h2>
        {loadingSaved ? (
          <p className="text-xs text-content-tertiary">Loading…</p>
        ) : saved.length === 0 ? (
          <EmptyState
            title="No saved hunts"
            description="Save a query you expect to run again and it will appear here."
          />
        ) : (
          <div className="space-y-2">
            {saved.map((hunt) => (
              <div
                key={hunt.id}
                className="flex items-center justify-between gap-3 flex-wrap border-b border-line-subtle last:border-0 pb-2 last:pb-0"
              >
                <div className="min-w-0">
                  <span className="text-sm font-medium text-content-primary">
                    {hunt.name}
                  </span>
                  <p className="text-[11px] font-mono text-content-tertiary mt-0.5">
                    {hunt.query}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setQuery(hunt.query);
                    void run(hunt.query);
                  }}
                >
                  <Play size={13} className="mr-1.5" /> Run
                </Button>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Modal open={saveOpen} onClose={() => setSaveOpen(false)} title="Save this hunt">
        <div className="space-y-4">
          <p className="text-xs text-content-secondary font-mono break-all">{query}</p>
          <div>
            <label
              className="tech-label text-content-tertiary block mb-1.5"
              htmlFor="hunt-name"
            >
              Name
            </label>
            <input
              id="hunt-name"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="Okta criticals"
              className="w-full bg-app-subtle border border-line-subtle rounded-sm px-3 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setSaveOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={save} disabled={!saveName.trim()}>
              Save hunt
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
