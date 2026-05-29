export const dynamic = "force-dynamic";
import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

const ADMIN_EMAILS = (process.env.ADMIN_EMAILS ?? "").split(",").map((s) => s.trim()).filter(Boolean);

/**
 * GET /api/feedback/export?format=jsonl&rating=1&limit=5000
 *
 * Admin-only. Exports feedback-rated Q&A pairs for fine-tuning.
 * format=jsonl  → one JSON object per line (chat format for fine-tuning)
 * format=csv    → CSV with headers
 * rating=1      → positive only | rating=-1 → negative only | omit → all
 */
export async function GET(req: NextRequest) {
  const session = await getServerSession(authOptions);
  const email = session?.user?.email ?? "";

  if (!ADMIN_EMAILS.includes(email)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const params = req.nextUrl.searchParams;
  const format = params.get("format") ?? "jsonl";
  const ratingParam = params.get("rating");
  const limit = Math.min(parseInt(params.get("limit") ?? "10000", 10), 50000);

  const ratingFilter =
    ratingParam === "1"  ? 1  :
    ratingParam === "-1" ? -1 : undefined;

  const feedbacks = await prisma.feedback.findMany({
    where:   ratingFilter !== undefined ? { rating: ratingFilter } : {},
    include: { queryLog: { select: { question: true, answer: true, sources: true, modelUsed: true } } },
    orderBy: { createdAt: "desc" },
    take:    limit,
  });

  if (format === "csv") {
    const rows = [
      ["id", "rating", "question", "answer", "model", "createdAt"],
      ...feedbacks.map((f) => [
        f.id,
        String(f.rating),
        `"${(f.queryLog.question ?? "").replace(/"/g, '""')}"`,
        `"${(f.queryLog.answer ?? "").replace(/"/g, '""').slice(0, 500)}"`,
        f.queryLog.modelUsed,
        f.createdAt.toISOString(),
      ]),
    ];
    const csv = rows.map((r) => r.join(",")).join("\n");
    return new NextResponse(csv, {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename="feedback_export_${Date.now()}.csv"`,
      },
    });
  }

  // Default: JSONL chat format (compatible with OpenAI fine-tuning & Bielik)
  const lines = feedbacks.map((f) => {
    const sources = (() => {
      try { return JSON.parse(f.queryLog.sources); } catch { return []; }
    })();

    return JSON.stringify({
      messages: [
        { role: "system", content: "Jesteś polskim asystentem prawnym. Odpowiadaj rzetelnie na podstawie aktów prawnych." },
        { role: "user",   content: f.queryLog.question },
        { role: "assistant", content: f.queryLog.answer },
      ],
      metadata: {
        rating:     f.rating,
        quality:    f.rating === 1 ? "good" : "bad",
        model:      f.queryLog.modelUsed,
        n_sources:  sources.length,
        created_at: f.createdAt.toISOString(),
        feedback_id: f.id,
      },
    });
  });

  return new NextResponse(lines.join("\n"), {
    headers: {
      "Content-Type": "application/x-ndjson; charset=utf-8",
      "Content-Disposition": `attachment; filename="feedback_finetune_${Date.now()}.jsonl"`,
    },
  });
}
