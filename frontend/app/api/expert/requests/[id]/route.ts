export const dynamic = "force-dynamic";
import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { sendMail } from "@/lib/mailer";

const BASE_URL = process.env.NEXTAUTH_URL || "http://localhost:3000";

function escHtml(s: string): string {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// PATCH — expert responds; or requester closes
export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  const { id } = await params;
  const request = await prisma.expertRequest.findUnique({
    where:   { id },
    include: { requester: { select: { email: true, name: true } } },
  });
  if (!request) return NextResponse.json({ error: "Nie znaleziono." }, { status: 404 });

  const body  = await req.json() as { response?: string; status?: string };
  const tier  = session.user.tier ?? "free";

  // Expert responds
  if (body.response !== undefined) {
    if (tier !== "kancelaria") return NextResponse.json({ error: "Tylko eksperci." }, { status: 403 });
    if (request.status !== "open") return NextResponse.json({ error: "Zapytanie już zamknięte." }, { status: 409 });

    const updated = await prisma.expertRequest.update({
      where: { id },
      data: {
        response:    body.response.trim().slice(0, 5000),
        expertId:    session.user.id,
        status:      "answered",
        respondedAt: new Date(),
      },
    });

    // Notify requester by email
    if (request.requester.email) {
      void sendMail({
        to:      request.requester.email,
        subject: "⚖️ LexCorpus: ekspert odpowiedział na Twoje pytanie",
        html:    `<!DOCTYPE html><html lang="pl"><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,sans-serif;background:#f8fafc;padding:32px 16px">
  <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:16px;padding:32px;box-shadow:0 1px 3px rgba(0,0,0,.1)">
    <h1 style="color:#1d4ed8;font-size:20px;margin:0 0 16px"><span style="opacity:.7">Lex</span>Corpus</h1>
    <p style="color:#0f172a;font-size:15px;margin:0 0 12px">Ekspert odpowiedział na Twoje pytanie prawne.</p>
    <blockquote style="border-left:3px solid #2563eb;padding:12px 16px;margin:0 0 20px;color:#475569;font-size:14px">
      ${escHtml(request.question.slice(0, 200))}${request.question.length > 200 ? "…" : ""}
    </blockquote>
    <a href="${BASE_URL}/expert" style="display:inline-block;background:#2563eb;color:#fff;padding:12px 24px;border-radius:10px;text-decoration:none;font-weight:600;font-size:14px">
      Zobacz odpowiedź →
    </a>
  </div>
</body></html>`,
      });
    }

    return NextResponse.json(updated);
  }

  // Requester closes own request
  if (body.status === "closed") {
    if (request.requesterId !== session.user.id) {
      return NextResponse.json({ error: "Brak uprawnień." }, { status: 403 });
    }
    const updated = await prisma.expertRequest.update({
      where: { id },
      data:  { status: "closed" },
    });
    return NextResponse.json(updated);
  }

  return NextResponse.json({ error: "Nieprawidłowe żądanie." }, { status: 400 });
}
