import { withAuth } from "next-auth/middleware";
import { NextResponse } from "next/server";

export default withAuth(
  function middleware() {
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
  ],
};
