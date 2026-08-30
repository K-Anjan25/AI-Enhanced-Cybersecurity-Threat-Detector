import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, Server } from "lucide-react";
import apiClient from "../../../api/client";
import {
  Button,
  Card,
  EmptyState,
  Modal,
  NumberInput,
  PageHeader,
  SkeletonCard,
  StatCard,
  Select,
  Badge,
} from "../../../components/ui";
import { useToast } from "../../../components/ui/Toast";
import { getApiError } from "../../../utils/getApiError";

/**
 * Asset inventory — the ground truth behind attack paths and the posture score.
 *
 * Criticality is what makes an asset a "crown jewel" for path search, so this
 * page exists to let an operator record reality. It deliberately starts empty:
 * inventing a Domain Controller would invent a crown jewel, and every downstream
 * number would inherit the fiction.
 */

interface AssetRow {
  id: number;
  name: string;
  asset_type: string;
  ip_address?: string | null;
  hostname?: string | null;
  criticality: number;
  business_unit?: string | null;
  owner?: string | null;
}

const asList = (v: unknown): AssetRow[] => (Array.isArray(v) ? (v as AssetRow[]) : []);

const critTone = (c: number): string => {
  if (c >= 5) return "text-status-critical";
  if (c >= 4) return "text-status-warning";
  return "text-content-secondary";
};

export default function AssetInventoryPage() {
  const [assets, setAssets] = useState<AssetRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const { push } = useToast();

  const [name, setName] = useState("");
  const [hostname, setHostname] = useState("");
  const [ip, setIp] = useState("");
  const [assetType, setAssetType] = useState("host");
  const [criticality, setCriticality] = useState(3);
  const [unit, setUnit] = useState("");
  const [owner, setOwner] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get("/risk-based/assets");
      setAssets(asList(res.data));
    } catch (e) {
      push(getApiError(e, "Could not load assets"), "error");
    } finally {
      setLoading(false);
    }
  }, [push]);

  useEffect(() => {
    void load();
  }, [load]);

  const reset = () => {
    setName("");
    setHostname("");
    setIp("");
    setAssetType("host");
    setCriticality(3);
    setUnit("");
    setOwner("");
  };

  const submit = async () => {
    if (!name.trim()) {
      push("Give the asset a name", "warning");
      return;
    }
    setSaving(true);
    try {
      await apiClient.post("/risk-based/assets", {
        name: name.trim(),
        asset_type: assetType,
        ip_address: ip.trim() || null,
        hostname: hostname.trim() || null,
        criticality,
        business_unit: unit.trim() || null,
        owner: owner.trim() || null,
      });
      push(`Recorded ${name.trim()}`);
      setOpen(false);
      reset();
      await load();
    } catch (e) {
      push(getApiError(e, "Could not save the asset"), "error");
    } finally {
      setSaving(false);
    }
  };

  const crownJewels = useMemo(() => assets.filter((a) => a.criticality >= 5), [assets]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Asset inventory"
        description="What you own and how much it matters. Criticality 5 marks a crown jewel, which is what attack-path search works backwards from."
        actions={
          <Button size="sm" onClick={() => setOpen(true)}>
            <Plus size={13} className="mr-1.5" /> Add asset
          </Button>
        }
      />

      {loading ? (
        <SkeletonCard />
      ) : assets.length === 0 ? (
        <EmptyState
          title="No assets recorded"
          description="Attack paths and the posture score are computed from this inventory, so they stay empty until you add what you actually own. Nothing is invented on your behalf."
          action={<Button size="sm" onClick={() => setOpen(true)}>Add your first asset</Button>}
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Assets" value={assets.length} />
            <StatCard label="Crown jewels" value={crownJewels.length} />
            <StatCard
              label="Business units"
              value={new Set(assets.map((a) => a.business_unit).filter(Boolean)).size}
            />
          </div>

          <Card className="p-5">
            <div className="space-y-2">
              {assets.map((a) => (
                <div
                  key={a.id}
                  className="flex items-center justify-between gap-3 flex-wrap border-b border-line-subtle last:border-0 pb-2 last:pb-0"
                >
                  <div className="min-w-0 flex items-center gap-2">
                    <Server size={13} className="text-content-tertiary shrink-0" aria-hidden />
                    <span className="text-sm font-medium text-content-primary">{a.name}</span>
                    {a.hostname && (
                      <span className="font-mono text-[11px] text-content-tertiary">{a.hostname}</span>
                    )}
                    {a.ip_address && (
                      <span className="font-mono text-[11px] text-content-tertiary">{a.ip_address}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {a.business_unit && (
                      <Badge className="bg-app-subtle text-content-tertiary border-line-subtle">
                        {a.business_unit}
                      </Badge>
                    )}
                    {a.owner && (
                      <span className="text-[11px] text-content-tertiary">{a.owner}</span>
                    )}
                    <span className={`text-xs font-mono font-bold ${critTone(a.criticality)}`}>
                      {a.criticality}/5
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title="Add asset">
        <div className="space-y-3">
          <label className="block">
            <span className="text-xs font-medium text-content-secondary">Name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Primary file server"
              className="mt-1 w-full bg-app-subtle border border-line-subtle rounded-sm px-3 py-2 text-sm text-content-primary focus:outline-none focus:border-accent-primary/40"
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-xs font-medium text-content-secondary">Hostname</span>
              <input
                value={hostname}
                onChange={(e) => setHostname(e.target.value)}
                placeholder="fileserver01"
                className="mt-1 w-full bg-app-subtle border border-line-subtle rounded-sm px-3 py-2 text-sm text-content-primary font-mono focus:outline-none focus:border-accent-primary/40"
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-content-secondary">IP address</span>
              <input
                value={ip}
                onChange={(e) => setIp(e.target.value)}
                placeholder="10.0.0.20"
                className="mt-1 w-full bg-app-subtle border border-line-subtle rounded-sm px-3 py-2 text-sm text-content-primary font-mono focus:outline-none focus:border-accent-primary/40"
              />
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Select
              label="Type"
              value={assetType}
              onChange={(e) => setAssetType(e.target.value)}
              options={[
                { value: "host", label: "Host" },
                { value: "service", label: "Service" },
                { value: "database", label: "Database" },
                { value: "cloud", label: "Cloud resource" },
                { value: "identity", label: "Identity" },
              ]}
            />
            <NumberInput
              label="Criticality (5 = crown jewel)"
              value={criticality}
              onChange={setCriticality}
              min={1}
              max={5}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-xs font-medium text-content-secondary">Business unit</span>
              <input
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                placeholder="Finance"
                className="mt-1 w-full bg-app-subtle border border-line-subtle rounded-sm px-3 py-2 text-sm text-content-primary focus:outline-none focus:border-accent-primary/40"
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-content-secondary">Owner</span>
              <input
                value={owner}
                onChange={(e) => setOwner(e.target.value)}
                placeholder="jo@acme.com"
                className="mt-1 w-full bg-app-subtle border border-line-subtle rounded-sm px-3 py-2 text-sm text-content-primary focus:outline-none focus:border-accent-primary/40"
              />
            </label>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" size="sm" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={submit} disabled={saving}>
              {saving ? "Saving…" : "Add asset"}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
