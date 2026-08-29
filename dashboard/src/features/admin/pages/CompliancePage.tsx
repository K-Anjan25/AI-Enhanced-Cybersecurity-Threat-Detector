import React, { useEffect, useState } from "react";
import { PageHeader, Card, Button } from "../../../components/ui";
import { fetchAuditVerify, fetchSoc2Evidence, downloadSoc2Pdf, type AuditVerify, type Soc2Bundle } from "../../../api/complianceApi";
import { getApiError } from "../../../utils/getApiError";
import { Download, ShieldCheck, Hash } from "lucide-react";

export default function CompliancePage(): React.ReactElement {
  const [verify, setVerify] = useState<AuditVerify | null>(null);
  const [bundle, setBundle] = useState<Soc2Bundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [days, setDays] = useState(90);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [v, b] = await Promise.all([fetchAuditVerify(1000), fetchSoc2Evidence(days)]);
      setVerify(v);
      setBundle(b);
    } catch (err: any) {
      setError(getApiError(err, "Failed to load compliance evidence"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [days]);

  const handleDownloadSoc2Pdf = async () => {
    setDownloading(true);
    try {
      const blob = await downloadSoc2Pdf(days);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `soc2-evidence-${days}d.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(getApiError(err, "Failed to download SOC2 PDF"));
    } finally {
      setDownloading(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <PageHeader title="Compliance Evidence" description="Phase 48: Evidence bundle PDF with chain-of-custody + hash verification, SOC2 controls mapping, tamper-evident audit log." />
        <p className="text-sm text-content-tertiary">Loading…</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader title="Compliance Evidence" description="Tamper-evident audit log hash chain (SHA256 prev_hash|action|actor|resource|details|timestamp), chain-of-custody per case, SOC2 evidence bundle mapping, PDF export with hash verification and honest limitations footer." />

      {error && <div role="alert" className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical">{error}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card padded>
          <h3 className="text-sm font-bold text-content-primary mb-2 flex items-center gap-2"><Hash size={14} /> Audit Chain Integrity</h3>
          {verify ? (
            <div className="space-y-2 text-xs">
              <div className="flex justify-between"><span className="text-content-tertiary">Total checked</span><span className="font-mono font-semibold">{verify.total_checked}</span></div>
              <div className="flex justify-between"><span className="text-content-tertiary">Verified</span><span className="font-mono font-semibold">{verify.verified}</span></div>
              <div className="flex justify-between"><span className="text-content-tertiary">Chain valid</span><span className={`font-bold ${verify.chain_valid ? "text-status-success" : "text-status-critical"}`}>{String(verify.chain_valid)}</span></div>
              <div className="flex flex-col gap-1"><span className="text-content-tertiary">Last hash</span><code className="font-mono text-[10px] break-all bg-app-subtle p-1 rounded">{verify.last_hash}</code></div>
              {verify.broken_at && <div className="text-status-critical">Broken at {verify.broken_at}: {verify.broken_details}</div>}
              <p className="text-[11px] text-content-tertiary pt-2">Hash = SHA256(prev_hash|action|actor|resource|details|timestamp). Genesis = 64 zeros. Verified via /api/v1/compliance/audit/verify.</p>
            </div>
          ) : <p className="text-xs text-content-tertiary">No verification data</p>}
        </Card>

        <Card padded>
          <h3 className="text-sm font-bold text-content-primary mb-2 flex items-center gap-2"><ShieldCheck size={14} /> SOC2 Evidence Bundle</h3>
          {bundle ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div><span className="text-content-tertiary">Period:</span> <span className="font-mono">{bundle.period_days}d</span></div>
                <div><span className="text-content-tertiary">Total logs:</span> <span className="font-mono">{bundle.total_logs}</span></div>
                <div><span className="text-content-tertiary">Generated:</span> <span className="font-mono text-[10px]">{new Date(bundle.generated_at).toLocaleString()}</span></div>
                <div><span className="text-content-tertiary">Chain valid:</span> <span className={bundle.chain_integrity.chain_valid ? "text-status-success font-bold" : "text-status-critical font-bold"}>{String(bundle.chain_integrity.chain_valid)}</span></div>
              </div>

              <div className="space-y-2">
                {Object.entries(bundle.controls).map(([cid, cdata]) => (
                  <div key={cid} className="p-2 rounded-lg bg-app-subtle border border-line-subtle">
                    <p className="text-xs font-semibold text-content-primary">{cid}: {cdata.control_name} <span className="text-[10px] text-content-tertiary">({cdata.evidence_count} evidences)</span></p>
                    <p className="text-[11px] text-content-tertiary">{cdata.description}</p>
                    {cdata.sample_logs.length > 0 && (
                      <ul className="mt-1 space-y-0.5">
                        {cdata.sample_logs.slice(0, 3).map((log, i) => (
                          <li key={i} className="text-[10px] font-mono text-content-secondary">{log.action} by {log.actor} @ {new Date(log.timestamp).toLocaleDateString()}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>

              <div className="flex gap-2 pt-2">
                <select value={days} onChange={(e) => setDays(parseInt(e.target.value))} className="px-2 py-1 rounded bg-app-subtle border border-line-subtle text-xs">
                  <option value={30}>30 days</option>
                  <option value={90}>90 days</option>
                  <option value={180}>180 days</option>
                  <option value={365}>365 days</option>
                </select>
                <Button variant="primary" size="sm" onClick={handleDownloadSoc2Pdf} disabled={downloading}><Download size={14} className="mr-1" />{downloading ? "Downloading…" : `Download SOC2 PDF (${days}d)`}</Button>
              </div>
            </div>
          ) : <p className="text-xs text-content-tertiary">No bundle</p>}
        </Card>
      </div>

      <Card padded>
        <h3 className="text-sm font-bold text-content-primary mb-2">Evidence Bundle PDF — Chain-of-Custody + Hash Verification (Phase 48)</h3>
        <p className="text-xs text-content-tertiary mb-3">Per-case evidence bundle PDF includes: case metadata, chain-of-custody timeline with per-entry hash/prev_hash, audit chain integrity, optional SOC2 mapping, generation timestamp/actor/org, honest limitations footer. PDF uncompressed (pageCompression=0) for test greppability. Download from case workspace: Evidence PDF button. Headers X-Chain-Last-Hash and X-Audit-Chain-Valid included.</p>
        <ul className="text-[11px] text-content-secondary list-disc pl-4 space-y-1">
          <li>Hash chain is SHA256(prev_hash|content), not Merkle tree, no external timestamp authority</li>
          <li>PDF itself is not signed; hash verification is for audit log chain, not PDF integrity</li>
          <li>Retention deletes old logs; checkpoint preserves last hash but not full history</li>
          <li>Chain-of-custody covers case timeline events (status changes, analyst actions, comments) as recorded in DB</li>
          <li>Generated on-demand from live DB rows; not stored immutably unless exported and stored externally</li>
        </ul>
      </Card>
    </div>
  );
}
