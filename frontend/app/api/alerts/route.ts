import { NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

/** GET /api/alerts — alerty prawne dla zalogowanego usera */
export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const alerts = await prisma.legalAlert.findMany({
    where:   { userId: session.user.id },
    orderBy: { createdAt: "desc" },
    take:    50,
    include: { change: true },
  });

  return NextResponse.json(
    alerts.map((a) => ({
      id:         a.id,
      read:       !!a.readAt,
      createdAt:  a.createdAt,
      similarity: a.similarity,
      question:   a.question,
      change: {
        id:         a.change.id,
        title:      a.change.title,
        sourceType: a.change.sourceType,
        year:       a.change.year,
        summary:    a.change.summary,
        url:        a.change.url,
        detectedAt: a.change.detectedAt,
      },
    }))
  );
}
