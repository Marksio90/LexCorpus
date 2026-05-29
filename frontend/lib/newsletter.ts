/**
 * newsletter.ts — generuje i wysyła tygodniowy digest zmian w prawie.
 *
 * Logika:
 * 1. Pobiera userów z newsletterEnabled=true którym nie wysłano w ciągu 6 dni
 * 2. Dla każdego: pobiera nieprzeczytane LegalAlert z ostatnich 7 dni
 * 3. Jeśli są alerty → generuje HTML i wysyła
 * 4. Aktualizuje newsletterLastSentAt
 */

import { prisma } from "@/lib/prisma";
import { sendMail } from "@/lib/mailer";

const BASE_URL = process.env.NEXTAUTH_URL || "http://localhost:3000";

const SOURCE_LABELS: Record<string, string> = {
  legislation:     "Ustawa / Rozporządzenie",
  judgment_nsa:    "Wyrok NSA/WSA",
  judgment_sn:     "Wyrok Sądu Najwyższego",
  judgment_tk:     "Wyrok Trybunału Konstytucyjnego",
  judgment_common: "Wyrok sądu powszechnego",
  judgment_kio:    "Wyrok KIO",
};

function formatDate(d: Date | string) {
  return new Date(d).toLocaleDateString("pl-PL", {
    day: "2-digit", month: "long", year: "numeric",
  });
}

function buildAlertRow(alert: {
  similarity: number;
  question:   string;
  change: {
    title:      string;
    sourceType: string;
    year:       number | null;
    summary:    string;
    url:        string | null;
    detectedAt: Date;
  };
}): string {
  const pct      = Math.round(alert.similarity * 100);
  const srcLabel = SOURCE_LABELS[alert.change.sourceType] ?? "Dokument";
  const link     = alert.change.url
    ? `<a href="${alert.change.url}" style="color:#2563eb;text-decoration:none">Otwórz dokument ↗</a>`
    : "";
  const askLink  = `<a href="${BASE_URL}/ask?q=${encodeURIComponent(alert.question)}" style="color:#2563eb;text-decoration:none">Zapytaj ponownie →</a>`;

  return `
  <tr>
    <td style="padding:16px 0;border-bottom:1px solid #e2e8f0">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <span style="background:#eff6ff;color:#1d4ed8;font-size:11px;padding:2px 8px;border-radius:20px;font-weight:600">
          ${srcLabel}${alert.change.year ? ` · ${alert.change.year}` : ""}
        </span>
        <span style="color:#f59e0b;font-size:11px;font-weight:700">${pct}% dopasowania</span>
      </div>
      <p style="margin:0 0 4px;font-weight:600;color:#0f172a;font-size:14px">${alert.change.title}</p>
      <p style="margin:0 0 8px;color:#475569;font-size:13px;line-height:1.5">${alert.change.summary}</p>
      <p style="margin:0 0 4px;color:#94a3b8;font-size:11px">
        Twoje pytanie: „${alert.question}"
      </p>
      <div style="margin-top:8px;font-size:12px;display:flex;gap:12px">
        ${link}
        ${askLink}
      </div>
    </td>
  </tr>`;
}

function buildHtml(email: string, alerts: Parameters<typeof buildAlertRow>[0][], date: string): string {
  const rows   = alerts.map(buildAlertRow).join("");
  const unsubUrl = `${BASE_URL}/api/newsletter/unsubscribe?email=${encodeURIComponent(email)}`;

  return `<!DOCTYPE html>
<html lang="pl">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:32px 16px">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1)">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#1d4ed8,#2563eb);padding:32px 40px">
            <h1 style="margin:0;color:#fff;font-size:24px;font-weight:700">
              <span style="opacity:.8">Lex</span>Corpus
            </h1>
            <p style="margin:4px 0 0;color:#bfdbfe;font-size:14px">
              Tygodniowy digest zmian w prawie · ${date}
            </p>
          </td>
        </tr>

        <!-- Intro -->
        <tr>
          <td style="padding:24px 40px 0">
            <p style="margin:0;color:#1e293b;font-size:15px">
              W tym tygodniu pojawiło się <strong>${alerts.length}</strong>
              ${alerts.length === 1 ? "zmiana" : alerts.length < 5 ? "zmiany" : "zmian"}
              w przepisach i orzecznictwie powiązanych z Twoimi pytaniami.
            </p>
          </td>
        </tr>

        <!-- Alerts -->
        <tr>
          <td style="padding:16px 40px 24px">
            <table width="100%" cellpadding="0" cellspacing="0">
              ${rows}
            </table>
          </td>
        </tr>

        <!-- CTA -->
        <tr>
          <td style="padding:0 40px 32px;text-align:center">
            <a href="${BASE_URL}/alerts"
               style="display:inline-block;background:#2563eb;color:#fff;padding:12px 28px;border-radius:10px;text-decoration:none;font-weight:600;font-size:14px">
              Zobacz wszystkie alerty →
            </a>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f8fafc;padding:20px 40px;border-top:1px solid #e2e8f0">
            <p style="margin:0;color:#94a3b8;font-size:12px;text-align:center">
              Otrzymujesz ten email ponieważ masz włączony newsletter w LexCorpus.<br>
              <a href="${unsubUrl}" style="color:#94a3b8">Wypisz się</a>
              &nbsp;·&nbsp;
              <a href="${BASE_URL}/ask" style="color:#94a3b8">Otwórz aplikację</a>
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>`;
}

function buildText(alerts: Parameters<typeof buildAlertRow>[0][]): string {
  const lines = ["LexCorpus — Tygodniowy digest zmian w prawie", ""];
  for (const a of alerts) {
    lines.push(`• ${a.change.title}`);
    lines.push(`  ${a.change.summary}`);
    lines.push(`  Twoje pytanie: „${a.question}"`);
    if (a.change.url) lines.push(`  ${a.change.url}`);
    lines.push("");
  }
  lines.push(`Wszystkie alerty: ${BASE_URL}/alerts`);
  return lines.join("\n");
}

export async function sendWeeklyNewsletters(): Promise<{ sent: number; skipped: number }> {
  const since = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  const sixDaysAgo = new Date(Date.now() - 6 * 24 * 60 * 60 * 1000);

  // Pobierz userów którzy chcą newsletter i nie dostali go w ciągu 6 dni
  const users = await prisma.user.findMany({
    where: {
      newsletterEnabled: true,
      email:             { not: null },
      OR: [
        { newsletterLastSentAt: null },
        { newsletterLastSentAt: { lt: sixDaysAgo } },
      ],
    },
    select: { id: true, email: true, newsletterLastSentAt: true },
  });

  let sent = 0, skipped = 0;
  const dateStr = formatDate(new Date());

  for (const user of users) {
    if (!user.email) { skipped++; continue; }

    // Pobierz nieprzeczytane alerty z ostatnich 7 dni
    const alerts = await prisma.legalAlert.findMany({
      where: {
        userId:    user.id,
        readAt:    null,
        createdAt: { gte: since },
      },
      orderBy: { similarity: "desc" },
      take:    10,
      include: { change: true },
    });

    if (alerts.length === 0) { skipped++; continue; }

    try {
      await sendMail({
        to:      user.email,
        subject: `⚖️ LexCorpus: ${alerts.length} ${alerts.length === 1 ? "zmiana" : "zmiany/zmian"} w prawie dotyczących Ciebie`,
        html:    buildHtml(user.email, alerts, dateStr),
        text:    buildText(alerts),
      });

      await prisma.user.update({
        where: { id: user.id },
        data:  { newsletterLastSentAt: new Date() },
      });

      sent++;
    } catch (err) {
      console.error(`[newsletter] Błąd wysyłania do ${user.email}:`, err);
      skipped++;
    }
  }

  return { sent, skipped };
}
