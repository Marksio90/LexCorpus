export const dynamic = "force-dynamic";
import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

// GET — for experts (kancelaria): open requests; for users: own requests
export async function GET(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  const role = req.nextUrl.searchParams.get("role"); // "expert" | "mine"
  const tier = session.user.tier ?? "free";

  if (role === "expert") {
    if (tier !== "kancelaria") return NextResponse.json({ error: "Tylko kancelaria." }, { status: 403 });
    const requests = await prisma.expertRequest.findMany({
      where:   { status: "open" },
      orderBy: { createdAt: "desc" },
      take:    50,
      include: { requester: { select: { name: true } } },
    });
    return NextResponse.json(requests);
  }

  // Own requests
  const requests = await prisma.expertRequest.findMany({
    where:   { requesterId: session.user.id },
    orderBy: { createdAt: "desc" },
    take:    20,
    include: { expert: { select: { name: true } } },
  });
  return NextResponse.json(requests);
}

// POST — user submits a request
export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  const body = await req.json() as { question?: string; context?: string };
  if (!body.question?.trim()) {
    return NextResponse.json({ error: "Brak pytania." }, { status: 400 });
  }

  // Free: 3 open requests max; pro: 10; kancelaria: unlimited
  const limits: Record<string, number> = { free: 3, pro: 10, kancelaria: 9999 };
  const tier  = session.user.tier ?? "free";
  const limit = limits[tier] ?? 3;

  const openCount = await prisma.expertRequest.count({
    where: { requesterId: session.user.id, status: "open" },
  });
  if (openCount >= limit) {
    return NextResponse.json({ error: `Osiągnięto limit ${limit} otwartych zapytań.` }, { status: 429 });
  }

  const request = await prisma.expertRequest.create({
    data: {
      requesterId: session.user.id,
      question:    body.question.trim().slice(0, 3000),
      context:     body.context?.trim().slice(0, 2000) || null,
    },
  });
  return NextResponse.json(request, { status: 201 });
}
