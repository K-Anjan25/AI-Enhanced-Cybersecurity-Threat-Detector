"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/store/userStore";
import { Card } from "@/components/ui/Card";
import { Alert } from "@/components/ui/Alert";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/utils/toastBridge";

export default function DashboardOverviewPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<any>(null);
  const { toast } = useToast();

  useEffect(() => {
    // Fetch dashboard stats from API
    // Example: analytics.getOverview(user.org_id).then(setStats).catch(() => toast.error("Failed to load stats"));
  }, [user?.org_id]);

  if (!user) {
    router.push("/");
    return null;
  }

  return (
    <div className="max-w-7xl mx-auto">
      <h1 className="text-3xl font-bold text-foreground mb-6">Dashboard</h1>
      
      {stats ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          {/* KPI cards go here */}
          {stats.total_alerts && (
            <Card className="p-6 border-left:4 var status-critical">
              <div className="text-3xl font-bold text-status-critical">{stats.total_alerts}</div>
              <div className="text-muted mt-1">Total Alerts</div>
            </Card>
          )}
          {/* More cards: critical, high, medium, low */}
        </div>
      ) : (
        <Skeleton className="h-64 w-full rounded-lg animate-pulse" />
      )}

      {/* Alerts section */}
      <Card className="mt-8 p-6">
        <h2 className="text-xl font-semibold text-foreground mb-4">Recent Alerts</h2>
        <div className="space-y-4">
          {/* Alert cards go here */}
          <Skeleton className="h-12 w-full rounded-lg animate-pulse" />
        </div>
      </Card>
    </div>
  );
}