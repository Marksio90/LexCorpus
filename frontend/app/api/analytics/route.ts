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
    totalQueries,
    queriesLast7,
    queriesLast30,
    dailyUsage,
    topSources,
    alertsTotal,
    alertsUnread,
    registrySubs,
    expertRequests,
  ] = await Promise.all([
    prisma.queryLog.count({ where: { userId } }),
    prisma.queryLog.count({ where: { userId, createdAt: { gte: since7 } } }),
    prisma.queryLog.count({ where: { userId, createdAt: { gte: since30 } } }),

    // Daily query counts for the last 30 days
    prisma.usageLog.findMany({
      where:   { userId, date: { gte: since30.toISOString().slice(0, 10) } },
      orderBy: { date: "asc" },
    }),

    // Top source types from recent query logs (parse JSON sources field)
    prisma.queryLog.findMany({
      where:   { userId, createdAt: { gte: since30 } },
      select:  { sources: true },
      take:    200,
    }),

    prisma.legalAlert.count({ where: { userId } }),
    prisma.legalAlert.count({ where: { userId, readAt: null } }),
    prisma.registrySubscription.count({ where: { userId } }),
    prisma.expertRequest.count({ where: { requesterId: userId } }),
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
