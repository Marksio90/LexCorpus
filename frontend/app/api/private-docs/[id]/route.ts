import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

/** DELETE /api/private-docs/:id — usuwa dokument i jego kolekcję Qdrant */
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

  // Usuń kolekcję Qdrant asynchronicznie (best-effort)
  const apiUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    .replace(":3000", ":8000");
  fetch(`${apiUrl}/private-collection/${session.user.id}`, { method: "DELETE" }).catch(() => {});

  return NextResponse.json({ ok: true });
}
