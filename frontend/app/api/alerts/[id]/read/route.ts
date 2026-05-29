export const dynamic = "force-dynamic";
import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

/** POST /api/alerts/:id/read — oznacza alert jako przeczytany */
export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const alert = await prisma.legalAlert.findUnique({ where: { id }, select: { userId: true } });
  if (!alert || alert.userId !== session.user.id) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  await prisma.legalAlert.update({
    where: { id },
    data:  { readAt: new Date() },
  });

  return NextResponse.json({ ok: true });
}
