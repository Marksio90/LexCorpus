import { NextRequest } from "next/server";
import { prisma } from "@/lib/prisma";

const API_URL = process.env.INTERNAL_API_URL || "http://api:8000";

function originAllowed(origin: string | null, allowedDomains: string): boolean {
  if (allowedDomains === "*") return true;
  if (!origin) return false;
  const domains = allowedDomains.split(",").map((d) => d.trim().toLowerCase());
  try {
    const host = new URL(origin).hostname.toLowerCase();
    return domains.some((d) => host === d || host.endsWith("." + d));
  } catch {
    return false;
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ token: string }> },
) {
  const { token } = await params;

  const config = await prisma.widgetConfig.findUnique({ where: { token } });
  if (!config || !config.enabled) {
    return new Response(JSON.stringify({ error: "Widget niedostępny." }), { status: 404 });
  }

  const origin = req.headers.get("origin");
  if (!originAllowed(origin, config.allowedDomains)) {
    return new Response(JSON.stringify({ error: "Niedozwolona domena." }), { status: 403 });
  }

  const body = await req.json() as { question?: string };
  if (!body.question?.trim()) {
    return new Response(JSON.stringify({ error: "Brak pytania." }), { status: 400 });
  }

  // Forward to FastAPI stream
  const upstream = await fetch(`${API_URL}/ask/stream`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question:          body.question,
      use_retrieval:     true,
      source_type_filter: null,
      top_k:             5,
    }),
  });

  if (!upstream.ok) {
    return new Response(JSON.stringify({ error: "Błąd serwera AI." }), { status: 502 });
  }

  // Increment request counter (fire and forget)
  void prisma.widgetConfig.update({
    where: { token },
    data:  { requestCount: { increment: 1 } },
  });

  const corsHeaders = {
    "Content-Type":                "text/event-stream",
    "Cache-Control":               "no-cache",
    "Connection":                  "keep-alive",
    "Access-Control-Allow-Origin": origin ?? "*",
  };

  return new Response(upstream.body, { headers: corsHeaders });
}

export async function OPTIONS(
  req: NextRequest,
  { params }: { params: Promise<{ token: string }> },
) {
  await params; // consume
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin":  req.headers.get("origin") ?? "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  });
}
