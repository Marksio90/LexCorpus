import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

/** DELETE /api/tokens/:id — revoke tokenu */
export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const token = await prisma.apiToken.findUnique({ where: { id }, select: { userId: true } });
  if (!token || token.userId !== session.user.id) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  await prisma.apiToken.update({
    where: { id },
    data:  { revokedAt: new Date() },
  });

  return NextResponse.json({ ok: true });
}
