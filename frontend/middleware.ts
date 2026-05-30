import { withAuth } from "next-auth/middleware";
import { NextResponse } from "next/server";

export default withAuth(
  function middleware(req) {
    const { pathname } = req.nextUrl;
    const token = req.nextauth.token as Record<string, unknown> | null;

    // Redirect new users (no onboarding) to /onboarding on first protected page visit
    if (
      token &&
      !token.onboardingCompletedAt &&
      pathname !== "/onboarding" &&
      !pathname.startsWith("/api/")
    ) {
      const url = req.nextUrl.clone();
      url.pathname = "/onboarding";
      return NextResponse.redirect(url);
    }

    return NextResponse.next();
  },
  {
    callbacks: {
      authorized: ({ token }) => !!token,
    },
  }
);

export const config = {
  matcher: [
    "/ask/:path*",
    "/search/:path*",
    "/compare/:path*",
    "/history/:path*",
    "/admin/:path*",
    "/account/:path*",
    "/upgrade/:path*",
    "/alerts/:path*",
    "/draft/:path*",
    "/analyze/:path*",
    "/registry/:path*",
    "/timeline/:path*",
    "/precedents/:path*",
    "/expert/:path*",
    "/analytics/:path*",
    "/documents/:path*",
  ],
};
