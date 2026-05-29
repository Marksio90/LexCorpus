import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

// Returns distinct acts that have at least one LegalChange recorded
export async function GET(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  const q = req.nextUrl.searchParams.get("q")?.trim() ?? "";

  const changes = await prisma.legalChange.findMany({
    where: q
      ? {
          OR: [
            { title:  { contains: q } },
            { actId:  { contains: q } },
          ],
        }
      : undefined,
    select:  { actId: true, title: true, sourceType: true, year: true, url: true, detectedAt: true },
    orderBy: { detectedAt: "desc" },
    take:    200,
  });

  // Deduplicate by actId — keep most recent
  const seen = new Map<string, typeof changes[0]>();
  for (const c of changes) {
    if (!seen.has(c.actId)) seen.set(c.actId, c);
  }

  // Count changes per actId
  const actIds = Array.from(seen.keys());
  const counts = await Promise.all(
    actIds.map((id) => prisma.legalChange.count({ where: { actId: id } })),
  );

  const result = actIds.map((id, i) => ({
    ...seen.get(id)!,
    changeCount: counts[i],
  }));

  return NextResponse.json(result.slice(0, 30));
}
