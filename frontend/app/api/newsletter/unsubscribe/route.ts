export const dynamic = "force-dynamic";
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET(req: NextRequest) {
  const email = req.nextUrl.searchParams.get("email");
  if (!email) {
    return new NextResponse("Brakuje parametru email.", { status: 400 });
  }

  const user = await prisma.user.findUnique({ where: { email } });
  if (!user) {
    return new NextResponse("Nie znaleziono użytkownika.", { status: 404 });
  }

  await prisma.user.update({
    where: { email },
    data:  { newsletterEnabled: false },
  });

  return new NextResponse(
    `<!DOCTYPE html><html lang="pl"><head><meta charset="utf-8">
<title>Wypisano z newslettera</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8fafc;display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#fff;border-radius:16px;padding:40px;max-width:400px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.1)}
h1{color:#0f172a;font-size:20px;margin:0 0 8px}p{color:#64748b;font-size:14px;margin:0 0 20px}
a{color:#2563eb;text-decoration:none;font-size:14px}a:hover{text-decoration:underline}</style>
</head><body>
<div class="card">
  <h1>Wypisano z newslettera</h1>
  <p>Nie będziesz już otrzymywać tygodniowego podsumowania zmian w prawie.<br>
  Możesz ponownie włączyć newsletter w ustawieniach konta.</p>
  <a href="/ask">← Wróć do aplikacji</a>
</div>
</body></html>`,
    { status: 200, headers: { "Content-Type": "text/html; charset=utf-8" } },
  );
}
