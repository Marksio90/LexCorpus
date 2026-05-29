import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ actId: string }> },
) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  const { actId } = await params;
  const decoded = decodeURIComponent(actId);

  const cursor = req.nextUrl.searchParams.get("cursor") ?? undefined;
  const take   = 20;

  const changes = await prisma.legalChange.findMany({
    where:   { actId: decoded },
    orderBy: { detectedAt: "desc" },
    take:    take + 1,
    cursor:  cursor ? { id: cursor } : undefined,
    skip:    cursor ? 1 : 0,
  });

  const hasMore = changes.length > take;
  const items   = hasMore ? changes.slice(0, take) : changes;
  const nextCursor = hasMore ? items[items.length - 1].id : null;

  return NextResponse.json({ items, nextCursor });
}
