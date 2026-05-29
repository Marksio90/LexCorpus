import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import type { SourceDocument } from "@/lib/types";

const MAX_HISTORY = 200;

/** GET /api/history — zwraca historię zalogowanego usera */
export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const rows = await prisma.queryLog.findMany({
    where:   { userId: session.user.id },
    orderBy: { createdAt: "desc" },
    take:    MAX_HISTORY,
  });

  const entries = rows.map((r) => ({
    id:            r.id,
    timestamp:     r.createdAt.toISOString(),
    question:      r.question,
    answer:        r.answer,
    sources:       (() => { try { return JSON.parse(r.sources) as SourceDocument[]; } catch { return []; } })(),
    model_used:    r.modelUsed,
    retrieval_used: r.retrievalUsed,
  }));

  return NextResponse.json(entries);
}

/** POST /api/history — zapisuje nowy wpis */
export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.json() as {
    question:      string;
    answer:        string;
    sources:       SourceDocument[];
    model_used:    string;
    retrieval_used: boolean;
  };

  const row = await prisma.queryLog.create({
    data: {
      userId:        session.user.id,
      question:      body.question,
      answer:        body.answer,
      sources:       JSON.stringify(body.sources ?? []),
      modelUsed:     body.model_used,
      retrievalUsed: body.retrieval_used ?? true,
    },
  });

  // Usuń nadmiarowe wpisy (keep newest MAX_HISTORY)
  const count = await prisma.queryLog.count({ where: { userId: session.user.id } });
  if (count > MAX_HISTORY) {
    const oldest = await prisma.queryLog.findMany({
      where:   { userId: session.user.id },
      orderBy: { createdAt: "asc" },
      take:    count - MAX_HISTORY,
      select:  { id: true },
    });
    await prisma.queryLog.deleteMany({ where: { id: { in: oldest.map((o) => o.id) } } });
  }

  return NextResponse.json({ id: row.id, timestamp: row.createdAt.toISOString() }, { status: 201 });
}

/** DELETE /api/history — usuwa całą historię usera */
export async function DELETE() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  await prisma.queryLog.deleteMany({ where: { userId: session.user.id } });
  return NextResponse.json({ ok: true });
}
