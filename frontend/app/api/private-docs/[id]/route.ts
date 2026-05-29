import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://api:8000";

/** DELETE /api/private-docs/:id — usuwa dokument (tylko rekord DB; czyszczenie Qdrant po stronie API) */
export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const doc = await prisma.privateDocument.findUnique({ where: { id }, select: { userId: true } });
  if (!doc || doc.userId !== session.user.id) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  await prisma.privateDocument.delete({ where: { id } });

  // Sprawdź czy user ma jeszcze inne dokumenty — usuń kolekcję tylko gdy jest pusta
  const remaining = await prisma.privateDocument.count({ where: { userId: session.user.id } });
  if (remaining === 0) {
    fetch(`${INTERNAL_API_URL}/private-collection/${session.user.id}`, { method: "DELETE" }).catch(() => {});
  }

  return NextResponse.json({ ok: true });
}
