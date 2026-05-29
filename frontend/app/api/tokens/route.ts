import { NextRequest, NextResponse } from "next/server";
import { createHash, randomBytes } from "node:crypto";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

const MAX_TOKENS = 10;

function hashToken(plain: string): string {
  return createHash("sha256").update(plain).digest("hex");
}

/** GET /api/tokens — lista tokenów zalogowanego usera */
export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const tokens = await prisma.apiToken.findMany({
    where:   { userId: session.user.id, revokedAt: null },
    orderBy: { createdAt: "desc" },
    select:  { id: true, name: true, prefix: true, createdAt: true, lastUsedAt: true, requestCount: true },
  });

  return NextResponse.json(tokens);
}

/** POST /api/tokens — generuje nowy token */
export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  // Tylko plan kancelaria
  if (session.user.tier !== "kancelaria") {
    return NextResponse.json({ error: "Tokeny API dostępne tylko w planie Kancelaria." }, { status: 403 });
  }

  const count = await prisma.apiToken.count({
    where: { userId: session.user.id, revokedAt: null },
  });
  if (count >= MAX_TOKENS) {
    return NextResponse.json({ error: `Limit ${MAX_TOKENS} aktywnych tokenów.` }, { status: 400 });
  }

  const { name } = await req.json() as { name?: string };
  if (!name?.trim()) return NextResponse.json({ error: "Nazwa tokenu jest wymagana." }, { status: 400 });

  // lxc_ prefix + 32 losowe bajty hex
  const plain = `lxc_${randomBytes(32).toString("hex")}`;
  const token = await prisma.apiToken.create({
    data: {
      userId:    session.user.id,
      name:      name.trim(),
      tokenHash: hashToken(plain),
      prefix:    plain.slice(0, 12),   // "lxc_" + 8 znaków
    },
  });

  // Zwracamy plaintext TYLKO raz — potem nie ma do niego dostępu
  return NextResponse.json({
    id:        token.id,
    name:      token.name,
    prefix:    token.prefix,
    createdAt: token.createdAt,
    token:     plain,          // ← tylko przy tworzeniu
  }, { status: 201 });
}
