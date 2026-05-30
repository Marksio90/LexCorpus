import { NextResponse } from "next/server";

const BASE_URL = process.env.NEXTAUTH_URL || "https://lexcorpus.pl";

export function GET() {
  const body = `User-agent: *
Allow: /
Allow: /login
Allow: /regulamin
Allow: /polityka-prywatnosci
Disallow: /admin
Disallow: /account
Disallow: /api/
Disallow: /ask
Disallow: /history

Sitemap: ${BASE_URL}/sitemap.xml
`;
  return new NextResponse(body, {
    headers: { "Content-Type": "text/plain" },
  });
}
