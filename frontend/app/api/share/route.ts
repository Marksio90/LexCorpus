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

  const token     = randomBytes(16).toString("base64url"); // 22-char URL-safe token
  const expiresAt = body.expiresInDays
    ? new Date(Date.now() + body.expiresInDays * 86_400_000)
    : null;

  const report = await prisma.sharedReport.create({
    data: {
      token,
      userId:   session.user.id,
      question: body.question.trim(),
      answer:   body.answer.trim(),
      sources:  JSON.stringify(body.sources ?? []),
      modelUsed: body.modelUsed ?? "unknown",
      expiresAt,
    },
  });

  const BASE_URL = process.env.NEXTAUTH_URL || "http://localhost:3000";
  return NextResponse.json({ url: `${BASE_URL}/share/${report.token}`, token: report.token });
}
