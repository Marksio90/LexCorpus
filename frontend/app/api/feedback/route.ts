import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

/**
 * POST /api/feedback
 * Body: { queryLogId: string, rating: 1 | -1, comment?: string }
 *
 * Upserts feedback for a query. Authenticated users get userId attached;
 * anonymous sessions are accepted (userId = null).
 */
export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);

  let body: { queryLogId?: string; rating?: number; comment?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { queryLogId, rating, comment } = body;

  if (!queryLogId || typeof queryLogId !== "string") {
    return NextResponse.json({ error: "queryLogId required" }, { status: 400 });
  }
  if (rating !== 1 && rating !== -1) {
    return NextResponse.json({ error: "rating must be 1 or -1" }, { status: 400 });
  }

  // Verify the query log exists
  const queryLog = await prisma.queryLog.findUnique({ where: { id: queryLogId } });
  if (!queryLog) {
    return NextResponse.json({ error: "QueryLog not found" }, { status: 404 });
  }

  const userId = session?.user?.id ?? null;

  const feedback = await prisma.feedback.upsert({
    where:  { queryLogId },
    update: { rating, comment: comment ?? null, userId, updatedAt: new Date() },
    create: { queryLogId, rating, comment: comment ?? null, userId },
  });

  return NextResponse.json({ id: feedback.id, rating: feedback.rating });
}

/**
 * GET /api/feedback?queryLogId=xxx
 * Returns current feedback for a specific query (any user can check their own).
 */
export async function GET(req: NextRequest) {
  const queryLogId = req.nextUrl.searchParams.get("queryLogId");
  if (!queryLogId) {
    return NextResponse.json({ error: "queryLogId required" }, { status: 400 });
  }

  const feedback = await prisma.feedback.findUnique({ where: { queryLogId } });
  if (!feedback) {
    return NextResponse.json({ rating: null });
  }

  return NextResponse.json({ id: feedback.id, rating: feedback.rating });
}
