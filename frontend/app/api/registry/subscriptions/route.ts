export const dynamic = "force-dynamic";
import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  const subs = await prisma.registrySubscription.findMany({
    where:   { userId: session.user.id },
    orderBy: { createdAt: "desc" },
  });
  return NextResponse.json(subs);
}

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  const body = await req.json() as { actId?: string; title?: string; url?: string };
  if (!body.actId?.trim() || !body.title?.trim()) {
    return NextResponse.json({ error: "Wymagane: actId, title." }, { status: 400 });
  }

  // Limit: free=5, pro=50, kancelaria=unlimited
  const tier = session.user.tier ?? "free";
  const limits: Record<string, number> = { free: 5, pro: 50, kancelaria: 9999 };
  const limit = limits[tier] ?? 5;

  const count = await prisma.registrySubscription.count({ where: { userId: session.user.id } });
  if (count >= limit) {
    return NextResponse.json(
      { error: `Osiągnięto limit ${limit} subskrypcji dla planu ${tier}.` },
      { status: 429 },
    );
  }

  try {
    const sub = await prisma.registrySubscription.create({
      data: {
        userId: session.user.id,
        actId:  body.actId.trim(),
        title:  body.title.trim(),
        url:    body.url?.trim() || null,
      },
    });
    return NextResponse.json(sub, { status: 201 });
  } catch {
    // unique constraint violation
    return NextResponse.json({ error: "Już subskrybujesz ten akt." }, { status: 409 });
  }
}
