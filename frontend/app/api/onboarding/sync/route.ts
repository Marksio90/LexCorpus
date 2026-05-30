export const dynamic = "force-dynamic";

/**
 * GET /api/onboarding/sync
 *
 * Called client-side on first load (or from onboarding page) to backfill the
 * `onboarding_done` cookie for users who completed onboarding before the cookie
 * was introduced, or after clearing cookies.
 *
 * Returns { done: true } and sets the cookie if the user already completed
 * onboarding in the DB.  Middleware checks the cookie, not the DB, so this
 * one-time call re-aligns the two.
 */
import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ done: false });

  const user = await prisma.user.findUnique({
    where: { id: session.user.id },
    select: { onboardingCompletedAt: true },
  });

  const done = !!user?.onboardingCompletedAt;
  const response = NextResponse.json({ done });

  if (done) {
    response.cookies.set("onboarding_done", "1", {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 60 * 60 * 24 * 365 * 10,
    });
  }

  return response;
}
