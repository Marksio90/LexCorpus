import { NextResponse } from "next/server";

const BASE_URL = process.env.NEXTAUTH_URL || "https://lexcorpus.pl";

const STATIC_PAGES = [
  { url: "/",                      changefreq: "weekly",  priority: "1.0" },
  { url: "/login",                 changefreq: "monthly", priority: "0.8" },
  { url: "/upgrade",               changefreq: "monthly", priority: "0.9" },
  { url: "/regulamin",             changefreq: "yearly",  priority: "0.3" },
  { url: "/polityka-prywatnosci",  changefreq: "yearly",  priority: "0.3" },
];

export function GET() {
  const now = new Date().toISOString().split("T")[0];
  const items = STATIC_PAGES.map(
    (p) => `  <url>
    <loc>${BASE_URL}${p.url}</loc>
    <lastmod>${now}</lastmod>
    <changefreq>${p.changefreq}</changefreq>
    <priority>${p.priority}</priority>
  </url>`
  ).join("\n");

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${items}
</urlset>`;

  return new NextResponse(xml, {
    headers: { "Content-Type": "application/xml" },
  });
}
