import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { sendWeeklyNewsletters } from "@/lib/newsletter";

const ADMIN_EMAILS    = (process.env.ADMIN_EMAILS ?? "").split(",").map((e) => e.trim()).filter(Boolean);
const INTERNAL_SECRET = process.env.NEWSLETTER_INTERNAL_SECRET ?? "";

export async function POST(req: NextRequest) {
  // Allow internal scheduler calls via shared secret
  if (INTERNAL_SECRET && req.headers.get("x-internal-secret") === INTERNAL_SECRET) {
    // authorized
  } else {
    const session = await getServerSession(authOptions);
    if (!session?.user?.email) {
      return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });
    }
    if (ADMIN_EMAILS.length === 0 || !ADMIN_EMAILS.includes(session.user.email)) {
      return NextResponse.json({ error: "Brak uprawnień." }, { status: 403 });
    }
  }

  try {
    const result = await sendWeeklyNewsletters();
    return NextResponse.json({ ok: true, ...result });
  } catch (err) {
    console.error("[newsletter/send]", err);
    return NextResponse.json({ error: "Błąd wysyłania newslettera." }, { status: 500 });
  }
}
