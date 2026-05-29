export const dynamic = "force-dynamic";
import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions, TIER_LIMITS } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

/** GET /api/usage — zwraca {used, limit, tier} dla zalogowanego usera */
export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const date  = today();
  const tier  = session.user.tier ?? "free";
  const limit = TIER_LIMITS[tier] ?? TIER_LIMITS.free;

  const log = await prisma.usageLog.findUnique({
    where: { userId_date: { userId: session.user.id, date } },
  });

  return NextResponse.json({ used: log?.count ?? 0, limit, tier });
}

/** POST /api/usage — inkrementuje licznik; zwraca 429 jeśli limit przekroczony */
export async function POST(_req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = session.user.id;
  const date   = today();
  const tier   = session.user.tier ?? "free";
  const limit  = TIER_LIMITS[tier] ?? TIER_LIMITS.free;

  // Upsert: increment or create
  const log = await prisma.usageLog.upsert({
    where:  { userId_date: { userId, date } },
    update: { count: { increment: 1 } },
    create: { userId, date, count: 1 },
  });

  if (log.count > limit) {
    // Roll back — przekroczono limit przed inkrementem
    await prisma.usageLog.update({
      where:  { userId_date: { userId, date } },
      data:   { count: { decrement: 1 } },
    });
    return NextResponse.json(
      { error: "Dzienny limit zapytań wyczerpany", used: log.count - 1, limit, tier },
      { status: 429 }
    );
  }

  return NextResponse.json({ used: log.count, limit, tier });
}
