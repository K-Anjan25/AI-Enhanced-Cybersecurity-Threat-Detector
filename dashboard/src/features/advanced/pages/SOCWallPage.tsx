import React, { useEffect, useState } from "react";
import { Card, Button, PageHeader, Spinner } from "../../../components/ui";
import apiClient from "../../../api/client";

export default function SOCWallPage() {
  const [metrics, setMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const res = await apiClient.get("/soc-tv/live");
      setMetrics(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    if (autoRefresh) {
      const id = setInterval(load, 5000);
      return () => clearInterval(id);
    }
  }, [autoRefresh]);

  return (
    <div className="space-y-6 bg-black text-white min-h-screen p-6 -m-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-widest">NOCTRA SOC TV WALL</h1>
          <p className="text-xs text-gray-400">Real-time SOC metrics — auto-refresh 5s — Phase 84</p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" onClick={() => setAutoRefresh(!autoRefresh)}>{autoRefresh ? "Pause" : "Resume"}</Button>
          <Button size="sm" onClick={load}>Refresh</Button>
        </div>
      </div>

      {loading && !metrics && <div className="flex justify-center py-20"><Spinner /></div>}

      {metrics && (
        <>
          <div className="grid grid-cols-4 gap-4">
            <Card className="p-6 bg-gray-900 border-gray-700"><div className="text-xs text-gray-400">TOTAL ALERTS</div><div className="text-4xl font-bold">{metrics.total_alerts}</div></Card>
            <Card className="p-6 bg-gray-900 border-gray-700"><div className="text-xs text-gray-400">ALERTS / MIN</div><div className="text-4xl font-bold text-yellow-400">{metrics.alerts_per_minute}</div></Card>
            <Card className="p-6 bg-gray-900 border-gray-700"><div className="text-xs text-gray-400">OPEN CASES</div><div className="text-4xl font-bold text-blue-400">{metrics.open_cases}</div></Card>
            <Card className="p-6 bg-gray-900 border-gray-700"><div className="text-xs text-gray-400">CRITICAL</div><div className="text-4xl font-bold text-red-500">{metrics.critical_alerts}</div></Card>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <Card className="p-4 bg-gray-900 border-gray-700">
              <h3 className="font-bold text-sm mb-3">SEVERITY BREAKDOWN</h3>
              <div className="space-y-2 text-xs">
                {Object.entries(metrics.severity_breakdown || {}).map(([k,v]: any) => (
                  <div key={k} className="flex justify-between"><span>{k}</span><span className="font-bold">{String(v)}</span></div>
                ))}
              </div>
            </Card>
            <Card className="p-4 bg-gray-900 border-gray-700">
              <h3 className="font-bold text-sm mb-3">TOP SOURCES</h3>
              <div className="space-y-2 text-xs">
                {(metrics.top_sources || []).map((s: any, i: number) => (
                  <div key={i} className="flex justify-between"><span>{s.source}</span><span>{s.count}</span></div>
                ))}
              </div>
            </Card>
            <Card className="p-4 bg-gray-900 border-gray-700">
              <h3 className="font-bold text-sm mb-3">LAST HOUR / 24H</h3>
              <div className="text-xs space-y-1"><div>Last Hour: {metrics.alerts_last_hour}</div><div>Last 24H: {metrics.alerts_last_24h}</div><div className="text-[10px] text-gray-500 mt-2">{metrics.timestamp}</div></div>
            </Card>
          </div>

          <Card className="p-4 bg-gray-900 border-gray-700">
            <h3 className="font-bold text-sm mb-3">LIVE ALERT FEED</h3>
            <div className="space-y-1 max-h-[300px] overflow-auto">
              {(metrics.recent_alerts || []).map((a: any) => (
                <div key={a.id} className="flex gap-3 text-xs p-2 bg-black/50 rounded border border-gray-800">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${a.severity==="CRITICAL"?"bg-red-500 text-white":a.severity==="HIGH"?"bg-orange-500 text-white":"bg-gray-700"}`}>{a.severity}</span>
                  <span className="text-gray-400">{a.source}</span>
                  <span className="flex-1 truncate">{a.message}</span>
                  <span className="text-gray-500">{a.created_at ? new Date(a.created_at).toLocaleTimeString() : ""}</span>
                </div>
              ))}
            </div>
          </Card>

          <pre className="p-4 bg-gray-950 rounded text-[10px] overflow-auto max-h-[200px] border border-gray-800">{JSON.stringify(metrics, null, 2)}</pre>
        </>
      )}
    </div>
  );
}
