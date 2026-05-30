export const dynamic = "force-dynamic";

import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { NextRequest } from "next/server";

const BACKEND = process.env.BACKEND_URL ?? "http://api:8000";
const INTERNAL_SECRET = process.env.INTERNAL_API_SECRET ?? "";

export async function POST(req: NextRequest): Promise<Response> {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return new Response(
      `data: ${JSON.stringify({ type: "error", detail: "Wymagane logowanie." })}\n\n`,
      { status: 401, headers: { "Content-Type": "text/event-stream" } },
    );
  }

  const body = await req.text();

  const upstream = await fetch(`${BACKEND}/ask/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Token": INTERNAL_SECRET,
      "X-User-Id": session.user.id ?? "",
      "X-User-Tier": (session.user as { tier?: string }).tier ?? "free",
    },
    body,
  });

  // Przekazujemy strumień SSE bezpośrednio do klienta
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
