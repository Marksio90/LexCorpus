export const dynamic = "force-dynamic";
import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  const userId = session.user.id;

  // Last 30 days range
  const since30 = new Date(Date.now() - 30 * 86_400_000);
  const since7  = new Date(Date.now() - 7  * 86_400_000);

  const [
    recentLogs,
    dailyUsage,
    alertsTotal,
    alertsUnread,
    registrySubs,
    expertRequests,
  ] = await Promise.all([
    // One query for all count variants + sources — filter in JS
    prisma.queryLog.findMany({
      where:   { userId, createdAt: { gte: since30 } },
      select:  { createdAt: true, sources: true },
      orderBy: { createdAt: "desc" },
      take:    5000,
    }),

    // Daily query counts for the last 30 days
    prisma.usageLog.findMany({
      where:   { userId, date: { gte: since30.toISOString().slice(0, 10) } },
      orderBy: { date: "asc" },
    }),

    prisma.legalAlert.count({ where: { userId } }),
    prisma.legalAlert.count({ where: { userId, readAt: null } }),
    prisma.registrySubscription.count({ where: { userId } }),
    prisma.expertRequest.count({ where: { requesterId: userId } }),
  ]);

  // Derive counts from single query result
  const queriesLast30 = recentLogs.length;
  const queriesLast7  = recentLogs.filter((l) => l.createdAt >= since7).length;
  const [totalQueries, topSources] = await Promise.all([
    queriesLast30 < 5000
      ? Promise.resolve(queriesLast30)  // no additional query needed when under limit
      : prisma.queryLog.count({ where: { userId } }),
    Promise.resolve(recentLogs.slice(0, 200)),
  ]);

  // Count source types from sources JSON
  const sourceCounts: Record<string, number> = {};
  for (const log of topSources) {
    try {
      let srcs: { source_type?: string }[] = [];
      try { srcs = JSON.parse(log.sources) as typeof srcs; } catch { /* skip malformed */ }
      for (const s of srcs) {
        if (s.source_type) sourceCounts[s.source_type] = (sourceCounts[s.source_type] ?? 0) + 1;
      }
    } catch { /* skip */ }
  }

  // Build last-30-days chart: one entry per day
  const chart: { date: string; count: number }[] = [];
  for (let i = 29; i >= 0; i--) {
    const d = new Date(Date.now() - i * 86_400_000).toISOString().slice(0, 10);
    const found = dailyUsage.find((u) => u.date === d);
    chart.push({ date: d, count: found?.count ?? 0 });
  }

  return NextResponse.json({
    totalQueries,
    queriesLast7,
    queriesLast30,
    chart,
    sourceCounts,
    alertsTotal,
    alertsUnread,
    registrySubs,
    expertRequests,
    tier: session.user.tier ?? "free",
  });
}
