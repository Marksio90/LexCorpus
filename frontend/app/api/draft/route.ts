export const dynamic = "force-dynamic";
import { NextRequest } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { DRAFT_TEMPLATES } from "@/lib/draft-templates";
import OpenAI from "openai";

function getOpenAI() {
  return new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
}

const SYSTEM_PROMPT = `Jesteś doświadczonym polskim prawnikiem specjalizującym się w sporządzaniu dokumentów prawnych.
Twoje dokumenty są:
- Zgodne z aktualnym polskim prawem
- Precyzyjne i kompletne
- Napisane profesjonalnym językiem prawniczym
- Gotowe do użycia (zawierają pola do uzupełnienia w formacie [POLE] tam gdzie brakuje danych)

Zawsze:
1. Zaczynaj dokument od nagłówka z miejscem i datą: "[Miejscowość], dnia [DATA]"
2. Podawaj pełne tytuły ustaw przy pierwszym przywołaniu
3. Kończ miejscem na podpisy stron
4. Używaj polskich znaków (ą, ę, ó, ś, ź, ż, ć, ń, ł)
5. NIE dodawaj komentarzy ani wyjaśnień poza treścią dokumentu — generujesz sam dokument`;

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return new Response(JSON.stringify({ error: "Nieautoryzowany." }), { status: 401 });
  }

  const body = await req.json() as { templateId: string; fields: Record<string, string> };
  const { templateId, fields } = body;

  const template = DRAFT_TEMPLATES.find((t) => t.id === templateId);
  if (!template) {
    return new Response(JSON.stringify({ error: "Nieznany szablon." }), { status: 400 });
  }

  const tier = session.user.tier ?? "free";
  if (template.tier === "pro" && tier === "free") {
    return new Response(JSON.stringify({ error: "Ten szablon wymaga planu Pro." }), { status: 403 });
  }

  // Build user prompt from filled fields
  const filledFields = template.fields
    .map((f) => `${f.label}: ${fields[f.key] ?? "(nie podano)"}`)
    .join("\n");

  const userPrompt = `Sporządź dokument: ${template.label}

Dane:
${filledFields}

Wskazówki prawne: ${template.systemHint}

Wygeneruj kompletny, gotowy do podpisania dokument.`;

  const stream = await getOpenAI().chat.completions.create({
    model:  process.env.OPENAI_MODEL ?? "gpt-4o-mini",
    stream: true,
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user",   content: userPrompt },
    ],
    temperature: 0.3,
    max_tokens:  2500,
  });

  const encoder = new TextEncoder();
  const readable = new ReadableStream({
    async start(controller) {
      try {
        for await (const chunk of stream) {
          const delta = chunk.choices[0]?.delta?.content;
          if (delta) {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ delta })}\n\n`));
          }
          if (chunk.choices[0]?.finish_reason === "stop") {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ done: true })}\n\n`));
          }
        }
      } catch (err) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ error: String(err) })}\n\n`));
      } finally {
        controller.close();
      }
    },
  });

  return new Response(readable, {
    headers: {
      "Content-Type":  "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection":    "keep-alive",
    },
  });
}
