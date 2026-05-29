import { NextRequest } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import OpenAI from "openai";

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
const ALLOWED_TYPES = ["application/pdf", "image/jpeg", "image/png", "image/webp"];

const SYSTEM_PROMPT = `Jesteś doświadczonym polskim prawnikiem i ekspertem od analizy dokumentów prawnych.
Twoim zadaniem jest szczegółowa analiza dostarczonego dokumentu.

Odpowiedz WYŁĄCZNIE w formacie JSON zgodnym z podaną strukturą. Nie dodawaj żadnego tekstu poza JSON.

Struktura odpowiedzi:
{
  "typ_dokumentu": "np. Umowa o pracę / Umowa najmu / NDA / etc.",
  "strony": ["Strona 1: nazwa/rola", "Strona 2: nazwa/rola"],
  "daty": {
    "zawarcia": "DD.MM.RRRR lub null",
    "obowiązywania_od": "DD.MM.RRRR lub null",
    "obowiązywania_do": "DD.MM.RRRR lub null",
    "inne": ["opis daty: DD.MM.RRRR"]
  },
  "kluczowe_postanowienia": [
    { "tytuł": "krótka nazwa", "treść": "jedno zdanie opisu" }
  ],
  "zobowiazania": {
    "strona_1": ["zobowiązanie 1", "zobowiązanie 2"],
    "strona_2": ["zobowiązanie 1", "zobowiązanie 2"]
  },
  "czerwone_flagi": [
    { "powaga": "wysoka|średnia|niska", "opis": "opis problemu", "fragment": "cytat z dokumentu (max 100 znaków)" }
  ],
  "podsumowanie": "2-3 zdania ogólnej oceny dokumentu z perspektywy prawnej",
  "rekomendacja": "podpisać_po_negocjacjach|podpisać|odrzucić|skonsultować_z_prawnikiem"
}`;

async function extractPdfText(buffer: Buffer): Promise<string> {
  // Dynamically import to avoid SSR issues
  // pdf-parse exports differently depending on module resolution
  const mod = await import("pdf-parse");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const pdfParse = ((mod as any).default ?? mod) as (buf: Buffer, opts?: { max?: number }) => Promise<{ text: string }>;
  const data = await pdfParse(buffer, { max: 20 }); // max 20 pages
  return data.text.trim();
}

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return new Response(JSON.stringify({ error: "Nieautoryzowany." }), { status: 401 });
  }

  const formData = await req.formData();
  const file = formData.get("file") as File | null;

  if (!file) {
    return new Response(JSON.stringify({ error: "Brak pliku." }), { status: 400 });
  }
  if (file.size > MAX_FILE_SIZE) {
    return new Response(JSON.stringify({ error: "Plik jest za duży (max 10 MB)." }), { status: 400 });
  }
  if (!ALLOWED_TYPES.includes(file.type)) {
    return new Response(JSON.stringify({ error: "Nieobsługiwany format. Użyj PDF, JPG lub PNG." }), { status: 400 });
  }

  const bytes  = await file.arrayBuffer();
  const buffer = Buffer.from(bytes);

  let messages: OpenAI.Chat.ChatCompletionMessageParam[];

  if (file.type === "application/pdf") {
    // Extract text from PDF, then send as text
    let text: string;
    try {
      text = await extractPdfText(buffer);
    } catch {
      return new Response(JSON.stringify({ error: "Nie udało się odczytać PDF. Spróbuj z plikiem obrazu." }), { status: 422 });
    }
    if (text.length < 50) {
      return new Response(JSON.stringify({ error: "PDF wydaje się być skanem bez warstwy tekstowej. Prześlij jako obraz." }), { status: 422 });
    }
    // Limit to ~12 000 chars to stay within context
    const truncated = text.length > 12000 ? text.slice(0, 12000) + "\n\n[… tekst obcięty …]" : text;
    messages = [
      { role: "system",  content: SYSTEM_PROMPT },
      { role: "user",    content: `Przeanalizuj poniższy dokument prawny:\n\n${truncated}` },
    ];
  } else {
    // Image — use GPT-4o vision
    const b64 = buffer.toString("base64");
    messages = [
      { role: "system", content: SYSTEM_PROMPT },
      {
        role: "user",
        content: [
          { type: "text",      text: "Przeanalizuj poniższy dokument prawny widoczny na obrazie:" },
          { type: "image_url", image_url: { url: `data:${file.type};base64,${b64}`, detail: "high" } },
        ],
      },
    ];
  }

  // Use GPT-4o for vision, mini for text (cheaper)
  const model = file.type !== "application/pdf"
    ? "gpt-4o"
    : (process.env.OPENAI_MODEL ?? "gpt-4o-mini");

  const stream = await openai.chat.completions.create({
    model,
    stream:      true,
    messages,
    temperature: 0.1,
    max_tokens:  2000,
    response_format: { type: "json_object" },
  });

  const encoder = new TextEncoder();
  const readable = new ReadableStream({
    async start(controller) {
      try {
        let fullJson = "";
        for await (const chunk of stream) {
          const delta = chunk.choices[0]?.delta?.content;
          if (delta) {
            fullJson += delta;
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
