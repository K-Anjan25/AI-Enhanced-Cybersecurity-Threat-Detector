import React, { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Globe, Info, RefreshCw, XCircle } from "lucide-react";
import apiClient from "../../../api/client";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Modal,
  PageHeader,
  RawData,
  SeverityBadge,
  SkeletonCard,
  StatCard,
} from "../../../components/ui";
import { useToast } from "../../../components/ui/Toast";
import { getApiError } from "../../../utils/getApiError";

/**
 * Attack surface — what the internet can see, and whether it is really there.
 *
 * These records are not just a list. Attack-path analysis treats every *open*
 * exposure as an attacker's entry point, so a wrong entry keeps generating
 * routes to crown jewels. Until now an operator could see the conclusion (on
 * the case page) but not the input, and had no way to retract a bad one.
 *
 * So the important control here is Dismiss. Marking an exposure fixed or not
 * a real finding removes it from attack-path search, which is why each row
 * shows its evidence: you should be able to judge the record before retracting
 * the conclusions drawn from it.
 */

interface Exposure {
  id: number;
  name: string;
  ip_address: string | null;
  port: number | null;
  service: string | null;
  exposure_type: string;
  severity: string;
  description: string | null;
  evidence: Record<string, unknown> | null;
  status: string;
  first_seen_at: string | null;
  last_seen_at: string | null;
}

interface Summary {
  total_exposures: number;
  open_exposures: number;
  high: number;
  critical: number;
  expired_certs: number;
}

const asList = (v: unknown): Exposure[] => (Array.isArray(v) ? (v as Exposure[]) : []);

const humanType = (raw: string): string =>
  raw.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

type Pending = { exposure: Exposure; status: "fixed" | "ignored" };

export default function AttackSurfacePage() {
  const [exposures, setExposures] = useState<Exposure[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [note, setNote] = useState("");
  const { push } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    const [list, totals] = await Promise.allSettled([
      apiClient.get("/exposure/"),
      apiClient.get("/exposure/summary"),
    ]);

    if (list.status === "fulfilled") {
      setExposures(asList(list.value.data));
      setFailed(false);
    } else {
      // An unreachable list is not an empty attack surface.
      setFailed(true);
      push(getApiError(list.reason, "Could not load the attack surface"), "error");
    }
    if (totals.status === "fulfilled") setSummary(totals.value.data as Summary);
    setLoading(false);
  }, [push]);

  useEffect(() => {
    void load();
  }, [load]);

  const submit = async () => {
    if (!pending) return;
    const { exposure, status } = pending;
    setBusy(true);
    try {
      await apiClient.post(`/exposure/${exposure.id}/status`, {
        status,
        note: note.trim() || null,
      });
      push(
        status === "ignored"
          ? `Dismissed ${exposure.name} — it will no longer be treated as a way in`
          : `Marked ${exposure.name} fixed`,
      );
      setPending(null);
      setNote("");
      await load();
    } catch (e) {
      push(getApiError(e, "Could not update the exposure"), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Attack surface"
        description="Hosts and services discoverable from outside. Anything still open is treated as a possible way in when attack paths are calculated."
        actions={
          <Button variant="secondary" size="sm" onClick={() => void load()} disabled={loading}>
            <RefreshCw size={13} className="mr-1.5" /> Refresh
          </Button>
        }
      />

      {loading ? (
        <SkeletonCard />
      ) : failed ? (
        <EmptyState
          title="Attack surface unavailable"
          description="The records could not be loaded. This is a failure, not an empty attack surface."
          action={
            <Button size="sm" onClick={() => void load()}>
              Try again
            </Button>
          }
        />
      ) : (
        <>
          {summary && (
            <div className="grid gap-4 sm:grid-cols-4">
              <StatCard label="Open" value={summary.open_exposures} />
              <StatCard
                label="Critical"
                value={summary.critical}
                tone={summary.critical > 0 ? "critical" : "default"}
              />
              <StatCard label="High" value={summary.high} />
              <StatCard label="Recorded in total" value={summary.total_exposures} />
            </div>
          )}

          <Card className="p-4">
            <div className="flex items-start gap-2">
              <Info size={14} className="text-content-tertiary shrink-0 mt-0.5" aria-hidden />
              <p className="text-xs text-content-secondary">
                Each open record is used as a starting point when working out how an
                attacker could reach a critical asset. If one is wrong, dismissing it here
                withdraws the attack paths built on it.
              </p>
            </div>
          </Card>

          {exposures.length === 0 ? (
            <EmptyState
              icon={<Globe size={20} />}
              title="Nothing exposed"
              description="No open exposures are recorded. Add a domain and run discovery to look for hosts published in certificate transparency logs."
            />
          ) : (
            <Card className="p-5">
              <div className="space-y-3">
                {exposures.map((e) => (
                  <div
                    key={e.id}
                    className="border-b border-line-subtle last:border-0 pb-3 last:pb-0"
                  >
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <SeverityBadge severity={e.severity} />
                          <span className="text-sm font-medium text-content-primary">
                            {e.name}
                          </span>
                          {e.port && (
                            <span className="text-xs font-mono text-content-tertiary">
                              :{e.port}
                            </span>
                          )}
                          <Badge className="bg-app-subtle text-content-tertiary border-line-subtle">
                            {humanType(e.exposure_type)}
                          </Badge>
                        </div>
                        {e.description && (
                          <p className="text-xs text-content-secondary mt-1">
                            {e.description}
                          </p>
                        )}
                        {e.ip_address && (
                          <p className="text-[11px] font-mono text-content-tertiary mt-0.5">
                            {e.ip_address}
                          </p>
                        )}
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() => setPending({ exposure: e, status: "ignored" })}
                        >
                          <XCircle size={13} className="mr-1.5" /> Not a finding
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          disabled={busy}
                          onClick={() => setPending({ exposure: e, status: "fixed" })}
                        >
                          <CheckCircle2 size={13} className="mr-1.5" /> Fixed
                        </Button>
                      </div>
                    </div>

                    {/* The evidence behind the record, so it can be judged. */}
                    {e.evidence && Object.keys(e.evidence).length > 0 && (
                      <div className="mt-2">
                        <RawData value={e.evidence} label="Evidence" />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          )}
        </>
      )}

      <Modal
        open={pending !== null}
        onClose={() => setPending(null)}
        title={
          pending?.status === "ignored" ? "Dismiss this exposure?" : "Mark as fixed?"
        }
      >
        <div className="space-y-4">
          <p className="text-xs text-content-secondary">
            {pending?.status === "ignored" ? (
              <>
                <span className="font-mono">{pending?.exposure.name}</span> will stop being
                treated as a way in, and any attack path that starts from it will be
                withdrawn. Say why, so the next person knows this was a judgement rather
                than an oversight.
              </>
            ) : (
              <>
                <span className="font-mono">{pending?.exposure.name}</span> will be recorded
                as closed. It stays in the history and will reappear if discovery finds it
                again.
              </>
            )}
          </p>
          <div>
            <label
              className="tech-label text-content-tertiary block mb-1.5"
              htmlFor="exposure-note"
            >
              Reason
            </label>
            <textarea
              id="exposure-note"
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Decommissioned in March; DNS no longer resolves"
              className="w-full bg-app-subtle border border-line-subtle rounded-sm px-3 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setPending(null)}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button size="sm" onClick={submit} disabled={busy}>
              {busy
                ? "Saving…"
                : pending?.status === "ignored"
                  ? "Dismiss exposure"
                  : "Mark fixed"}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
