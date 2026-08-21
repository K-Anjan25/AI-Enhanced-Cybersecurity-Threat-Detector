import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, Inbox, CircleCheck, Radar, ChevronRight } from "lucide-react";
import { PageHeader, Card, StatCard, Button, SeverityBadge, EmptyState, SkeletonCard } from "../components/ui";
import AnalystApi from "../api/analystApi";
import type { Brief } from "../types/analyst";

/**
 * The analyst's calm home. "Here's where things stand" — a few numbers, the
 * cases that need a human decision, and one button to see the loop in action.
 */
const BriefPage: React.FC = () => {
  const navigate = useNavigate();
  const [brief, setBrief] = useState<Brief | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [simulating, setSimulating] = useState(false);

  const loadBrief = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setBrief(await AnalystApi.fetchBrief());
    } catch (err: any) {
      setError(err?.detail || "Failed to load your brief");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBrief();
  }, [loadBrief]);

  const handleSimulate = async () => {
    setSimulating(true);
    setError(null);
    try {
      const created = await AnalystApi.simulate();
      navigate(`/case/${created.id}`);
    } catch (err: any) {
      setError(err?.detail || "Could not simulate an incident");
      setSimulating(false);
    }
  };

  const pending = brief?.top_cases ?? [];

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Here's where things stand"
        description="Your NOCTRA analyst watches quietly and only asks when a decision is yours to make."
        actions={
          <Button variant="primary" onClick={handleSimulate} disabled={simulating}>
            <Sparkles size={16} className="mr-1.5" aria-hidden />
            {simulating ? "Simulating…" : "Simulate incident"}
          </Button>
        }
      />

      {error && (
        <div className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical">
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatCard
            label="Needs your decision"
            value={brief?.pending_count ?? 0}
            hint={brief?.pending_count ? "Waiting on a human" : "All clear"}
            tone={brief?.pending_count ? "warning" : "success"}
            icon={<Inbox size={18} aria-hidden />}
          />
          <StatCard
            label="Handled today"
            value={brief?.handled_today ?? 0}
            hint="Decisions recorded"
            tone="success"
            icon={<CircleCheck size={18} aria-hidden />}
          />
          <StatCard
            label="Assets watched"
            value={brief?.watching ?? 0}
            hint="Across your environment"
            tone="accent"
            icon={<Radar size={18} aria-hidden />}
          />
        </div>
      )}

      <Card padded={false} className="overflow-hidden">
        <div className="px-5 py-4 border-b border-line-subtle">
          <h2 className="text-sm font-semibold text-content-primary font-display tracking-tight">
            What needs you
          </h2>
          <p className="text-xs text-content-tertiary mt-0.5">
            Open cases where your analyst has drafted an action and is waiting for your call.
          </p>
        </div>

        {loading ? (
          <div className="p-5 space-y-3">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : pending.length === 0 ? (
          <EmptyState
            title="Nothing needs you right now"
            description="When something worth your attention happens, it shows up here. Try “Simulate incident” to see how it works."
          />
        ) : (
          <ul className="divide-y divide-line-subtle">
            {pending.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => navigate(`/case/${c.id}`)}
                  className="w-full flex items-center gap-3 px-5 py-4 text-left hover:bg-app-subtle/50 transition-colors"
                >
                  <SeverityBadge severity={c.priority} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-content-primary font-medium truncate">
                      {c.analysis?.headline || c.title}
                    </p>
                    {c.proposed_action && (
                      <p className="text-xs text-content-tertiary truncate mt-0.5">
                        Proposed: <span className="font-mono">{c.proposed_action.action_type}</span> on{" "}
                        {c.proposed_action.target}
                      </p>
                    )}
                  </div>
                  <ChevronRight size={16} className="text-content-tertiary shrink-0" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
};

export default BriefPage;
