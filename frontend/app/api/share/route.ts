export const dynamic = "force-dynamic";
import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { randomBytes } from "crypto";

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  const body = await req.json() as {
    question: string;
    answer:   string;
    sources:  unknown[];
    modelUsed: string;
    expiresInDays?: number;
  };

  if (!body.question?.trim() || !body.answer?.trim()) {
    return NextResponse.json({ error: "Wymagane: question, answer." }, { status: 400 });
  }
  if (body.question.length > 2000 || body.answer.length > 20000) {
    return NextResponse.json({ error: "Treść zbyt długa." }, { status: 400 });
  }

  const days      = Math.max(1, Math.min(365, body.expiresInDays ?? 30));
  const token     = randomBytes(16).toString("base64url"); // 22-char URL-safe token
  const expiresAt = new Date(Date.now() + days * 86_400_000);

  const report = await prisma.sharedReport.create({
    data: {
      token,
      userId:   session.user.id,
      question: body.question.trim(),
      answer:   body.answer.trim().slice(0, 20000),
      sources:  JSON.stringify(body.sources ?? []),
      modelUsed: body.modelUsed ?? "unknown",
      expiresAt,
    },
  });

  const BASE_URL = process.env.NEXTAUTH_URL || "http://localhost:3000";
  return NextResponse.json({ url: `${BASE_URL}/share/${report.token}`, token: report.token });
}
