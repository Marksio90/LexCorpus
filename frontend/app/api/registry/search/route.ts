export const dynamic = "force-dynamic";
import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";

const API_URL = process.env.INTERNAL_API_URL || "http://api:8000";

export async function GET(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  const q = req.nextUrl.searchParams.get("q")?.trim();
  if (!q || q.length < 2) return NextResponse.json([]);

  try {
    const res = await fetch(
      `${API_URL}/search`,
      {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query:             q,
          top_k:             12,
          source_type_filter: req.nextUrl.searchParams.get("type") ?? null,
        }),
      },
    );

    if (!res.ok) return NextResponse.json([]);

    const data = await res.json() as {
      results: {
        act_id:      string;
        title:       string;
        source_type: string;
        year:        number | null;
        url:         string | null;
        score:       number;
      }[];
    };

    // Deduplicate by act_id, keep highest score
    const seen = new Map<string, typeof data.results[0]>();
    for (const r of data.results) {
      if (!seen.has(r.act_id) || r.score > seen.get(r.act_id)!.score) {
        seen.set(r.act_id, r);
      }
    }

    return NextResponse.json(Array.from(seen.values()).slice(0, 8));
  } catch {
    return NextResponse.json([]);
  }
}
