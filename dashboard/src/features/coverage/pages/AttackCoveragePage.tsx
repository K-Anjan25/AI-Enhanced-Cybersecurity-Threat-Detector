import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, ShieldAlert } from "lucide-react";
import apiClient from "../../../api/client";
import {
  Button,
  Card,
  EmptyState,
  PageHeader,
  SkeletonCard,
  StatCard,
  Badge,
} from "../../../components/ui";
import { useToast } from "../../../components/ui/Toast";
import { getApiError } from "../../../utils/getApiError";

/**
 * Detection coverage — which ATT&CK techniques you could actually catch.
 *
 * Every row is derived from real artefacts in this tenant: alerts carrying a
 * technique ID, hunt queries mentioning it, named playbooks and purple-team
 * exercises. A technique with no matching artefact is reported as a gap rather
 * than quietly scored as covered.
 */

interface CoverageRow {
  id: number;
  tactic: string;
  technique_id: string;
  technique_name: string;
  has_rule: boolean;
  has_hunt: boolean;
  has_playbook: boolean;
  has_exercise: boolean;
  detection_count: number;
  coverage_score: number;
  gap_reason?: string | null;
  recommendation?: string | null;
}

const asList = (v: unknown): CoverageRow[] => (Array.isArray(v) ? (v as CoverageRow[]) : []);

const scoreTone = (score: number): string => {
  if (score >= 75) return "text-status-success";
  if (score >= 50) return "text-status-warning";
  if (score > 0) return "text-status-critical";
  return "text-content-tertiary";
};

const Signal: React.FC<{ on: boolean; label: string }> = ({ on, label }) => (
  <span
    title={on ? `${label}: present` : `${label}: missing`}
    className={`text-[10px] font-mono px-1.5 py-0.5 rounded-sm border ${
      on
        ? "border-accent-primary/40 text-accent-primary bg-accent-primary/10"
        : "border-line-subtle text-content-tertiary"
    }`}
  >
    {label}
  </span>
);

export default function AttackCoveragePage() {
  const [rows, setRows] = useState<CoverageRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const { push } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get("/attack-coverage/");
      setRows(asList(res.data));
    } catch (e) {
      push(getApiError(e, "Could not load detection coverage"), "error");
    } finally {
      setLoading(false);
    }
  }, [push]);

  useEffect(() => {
    void load();
  }, [load]);

  const reevaluate = async () => {
    setBusy(true);
    try {
      const res = await apiClient.post("/attack-coverage/evaluate");
      const next = asList(res.data);
      setRows(next);
      push(`Re-evaluated ${next.length} technique(s)`);
    } catch (e) {
      push(getApiError(e, "Re-evaluation failed"), "error");
    } finally {
      setBusy(false);
    }
  };

  const covered = rows.filter((r) => r.coverage_score > 0);
  const gaps = rows.filter((r) => r.coverage_score === 0);
  const percent = rows.length ? Math.round((covered.length / rows.length) * 100) : 0;

  const byTactic = rows.reduce<Record<string, CoverageRow[]>>((acc, r) => {
    (acc[r.tactic] ??= []).push(r);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <PageHeader
        title="Detection coverage"
        description="Which ATT&CK techniques you could actually catch, based on the rules, hunts, playbooks and exercises that exist in this tenant."
        actions={
          <Button variant="secondary" size="sm" onClick={reevaluate} disabled={busy || loading}>
            <RefreshCw size={13} className="mr-1.5" /> Re-evaluate
          </Button>
        }
      />

      {loading ? (
        <SkeletonCard />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No coverage evaluated yet"
          description="Run an evaluation to compare your detection artefacts against the ATT&CK techniques NOCTRA tracks."
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Techniques tracked" value={rows.length} />
            <StatCard label="With some coverage" value={`${percent}%`} />
            <StatCard label="Uncovered" value={gaps.length} />
          </div>

          {gaps.length > 0 && (
            <Card className="p-5">
              <div className="flex items-center gap-2 mb-3">
                <ShieldAlert size={15} className="text-status-critical" aria-hidden />
                <h2 className="text-sm font-bold font-display text-content-primary">
                  Biggest gaps
                </h2>
              </div>
              <div className="space-y-2">
                {gaps.slice(0, 5).map((r) => (
                  <div key={r.id} className="text-xs border-l-2 border-status-critical/40 pl-3">
                    <span className="font-mono text-content-primary">{r.technique_id}</span>{" "}
                    <span className="text-content-secondary">{r.technique_name}</span>
                    {r.recommendation && (
                      <p className="text-content-tertiary mt-0.5">{r.recommendation}</p>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          )}

          <div className="space-y-4">
            {Object.entries(byTactic).map(([tactic, techniques]) => (
              <Card key={tactic} className="p-5">
                <h2 className="text-xs font-bold uppercase tracking-wider text-content-tertiary mb-3">
                  {tactic}
                </h2>
                <div className="space-y-2">
                  {techniques.map((r) => (
                    <div
                      key={r.id}
                      className="flex items-center justify-between gap-3 flex-wrap border-b border-line-subtle last:border-0 pb-2 last:pb-0"
                    >
                      <div className="min-w-0">
                        <span className="font-mono text-xs text-content-primary">
                          {r.technique_id}
                        </span>{" "}
                        <span className="text-xs text-content-secondary">{r.technique_name}</span>
                        {r.detection_count > 0 && (
                          <Badge className="ml-2 bg-app-subtle text-content-tertiary border-line-subtle">
                            {r.detection_count} seen
                          </Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <Signal on={r.has_rule} label="rule" />
                        <Signal on={r.has_hunt} label="hunt" />
                        <Signal on={r.has_playbook} label="playbook" />
                        <Signal on={r.has_exercise} label="exercise" />
                        <span
                          className={`text-xs font-mono font-bold w-10 text-right ${scoreTone(r.coverage_score)}`}
                        >
                          {r.coverage_score}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
