export const dynamic = "force-dynamic";
import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function POST() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  await prisma.user.update({
    where: { id: session.user.id },
    data:  { onboardingCompletedAt: new Date() },
  });

  const response = NextResponse.json({ ok: true });
  // Set cookie so middleware can gate on onboarding without a DB lookup.
  // httpOnly=false so Next.js middleware (Edge runtime) can read it too.
  response.cookies.set("onboarding_done", "1", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24 * 365 * 10, // 10 years
  });
  return response;
}
