export const dynamic = "force-dynamic";
import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import OpenAI from "openai";

function getOpenAI() {
  return new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
}
const API_URL = process.env.INTERNAL_API_URL || "http://api:8000";

const JUDGMENT_TYPES = ["judgment_nsa", "judgment_sn", "judgment_tk", "judgment_common", "judgment_kio"];

interface SearchHit {
  act_id:      string;
  title:       string;
  source_type: string;
  year:        number | null;
  url:         string | null;
  score:       number;
  text:        string;
  chunk_index: number;
}

async function expandFactsToQuery(facts: string): Promise<string> {
  try {
    const resp = await getOpenAI().chat.completions.create({
      model:       process.env.OPENAI_MODEL ?? "gpt-4o-mini",
      temperature: 0.2,
      max_tokens:  120,
      messages: [
        {
          role:    "system",
          content: "Jesteś pomocnikiem prawnym. Przekształć opis stanu faktycznego w zwięzłe zapytanie prawnicze (max 2 zdania) nadające się do wyszukiwania w bazie orzeczeń sądowych. Użyj terminologii prawniczej. Odpowiedz TYLKO zapytaniem, bez wstępu.",
        },
        { role: "user", content: facts },
      ],
    });
    return resp.choices[0]?.message?.content?.trim() ?? facts;
  } catch {
    return facts;
  }
}

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  const body = await req.json() as {
    facts:       string;
    sourceTypes: string[];   // subset of JUDGMENT_TYPES
    topK:        number;
  };

  if (!body.facts?.trim()) {
    return NextResponse.json({ error: "Brak opisu stanu faktycznego." }, { status: 400 });
  }

  const facts       = body.facts.trim().slice(0, 3000);
  const topK        = Math.min(body.topK ?? 12, 20);
  const sourceTypes = (body.sourceTypes ?? JUDGMENT_TYPES)
    .filter((t) => JUDGMENT_TYPES.includes(t));

  // Expand facts to legal query
  const expandedQuery = await expandFactsToQuery(facts);

  // Search all requested source types in parallel
  const searches = await Promise.allSettled(
    sourceTypes.map((st) =>
      fetch(`${API_URL}/search`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query:              expandedQuery,
          top_k:              Math.ceil(topK / sourceTypes.length) + 2,
          source_type_filter: st,
        }),
      })
        .then((r) => r.ok ? r.json() as Promise<{ results?: SearchHit[] }> : { results: [] })
        .then((d) => (d.results ?? []).map((r) => ({ ...r, source_type: st }))),
    ),
  );

  // Merge, sort by score, dedup by act_id+chunk_index
  const all: SearchHit[] = [];
  for (const s of searches) {
    if (s.status === "fulfilled") all.push(...s.value);
  }

  const seen = new Set<string>();
  const deduped: SearchHit[] = [];
  for (const hit of all.sort((a, b) => b.score - a.score)) {
    const key = `${hit.act_id}__${hit.chunk_index}`;
    if (!seen.has(key)) { seen.add(key); deduped.push(hit); }
  }

  return NextResponse.json({
    expandedQuery,
    results: deduped.slice(0, topK),
  });
}
