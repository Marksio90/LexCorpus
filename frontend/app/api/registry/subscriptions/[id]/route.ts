import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  const { id } = await params;
  const sub = await prisma.registrySubscription.findUnique({ where: { id } });

  if (!sub || sub.userId !== session.user.id) {
    return NextResponse.json({ error: "Nie znaleziono." }, { status: 404 });
  }

  await prisma.registrySubscription.delete({ where: { id } });
  return new NextResponse(null, { status: 204 });
}
