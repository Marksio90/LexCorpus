import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  const user = await prisma.user.findUnique({
    where:  { id: session.user.id },
    select: { newsletterEnabled: true, tier: true, email: true, name: true, createdAt: true },
  });
  return NextResponse.json(user);
}

export async function PATCH(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  const body = await req.json() as { newsletterEnabled?: boolean };
  const data: Record<string, unknown> = {};

  if (typeof body.newsletterEnabled === "boolean") {
    data.newsletterEnabled = body.newsletterEnabled;
  }

  if (Object.keys(data).length === 0) {
    return NextResponse.json({ error: "Brak zmian." }, { status: 400 });
  }

  const user = await prisma.user.update({
    where:  { id: session.user.id },
    data,
    select: { newsletterEnabled: true },
  });
  return NextResponse.json(user);
}
