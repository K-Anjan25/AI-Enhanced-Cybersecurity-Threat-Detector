"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/store/userStore";
import { Sidebar } from "@/components/layout/Sidebar";
import { Navbar } from "@/components/layout/Navbar";
import { analytics } from "@/lib/api";

export default function DashboardLayout({
  children,
}: { children: ReactNode }) {
  const { user, orgId, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    // Optional: fetch org-level stats on dashboard enter
    // analytics.getOverview(orgId).then(...).catch(...);
  }, [user, orgId]);

  if (!user) {
    router.push("/");
    return null;
  }

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <Sidebar />
      <main className="flex-1 p-6 sm:p-8 lg:p-12 overflow-x-auto">
        {children}
      </main>
    </div>
  );
}