import { sendMail } from "@/lib/mailer";

const BASE_URL = process.env.NEXTAUTH_URL || "http://localhost:3000";

export async function sendWelcomeEmail(email: string): Promise<void> {
  const html = `<!DOCTYPE html>
<html lang="pl">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:32px 16px">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1)">

        <tr>
          <td style="background:linear-gradient(135deg,#1d4ed8,#2563eb);padding:40px">
            <h1 style="margin:0;color:#fff;font-size:28px;font-weight:700">
              <span style="opacity:.75">Lex</span>Corpus
            </h1>
            <p style="margin:6px 0 0;color:#bfdbfe;font-size:15px">
              Witaj w polskim AI do prawa
            </p>
          </td>
        </tr>

        <tr>
          <td style="padding:32px 40px">
            <p style="margin:0 0 16px;color:#0f172a;font-size:16px;line-height:1.6">
              Cześć! 👋<br><br>
              Twoje konto LexCorpus jest gotowe. Możesz już zadawać pytania prawne
              i otrzymywać odpowiedzi z cytatami z polskich aktów prawnych i orzecznictwa.
            </p>

            <div style="background:#f1f5f9;border-radius:12px;padding:20px;margin:24px 0">
              <p style="margin:0 0 12px;font-weight:600;color:#1e293b;font-size:14px">Co możesz zrobić:</p>
              <ul style="margin:0;padding:0 0 0 20px;color:#475569;font-size:14px;line-height:2">
                <li>Pytaj o przepisy prawa — z cytatami z ISAP</li>
                <li>Przeglądaj orzecznictwo NSA, SN, TK</li>
                <li>Śledź zmiany w prawie (alerty tygodniowe)</li>
                <li>Generuj szkice dokumentów prawnych</li>
              </ul>
            </div>

            <div style="margin:8px 0 0;font-size:13px;color:#64748b;background:#eff6ff;border-radius:10px;padding:14px 18px;border-left:3px solid #2563eb">
              <strong>Plan Free:</strong> 20 zapytań / dzień — bezpłatnie na zawsze.
              Potrzebujesz więcej? <a href="${BASE_URL}/upgrade" style="color:#2563eb">Sprawdź plan Pro</a>.
            </div>
          </td>
        </tr>

        <tr>
          <td style="padding:0 40px 32px;text-align:center">
            <a href="${BASE_URL}/ask"
               style="display:inline-block;background:#2563eb;color:#fff;padding:14px 32px;border-radius:10px;text-decoration:none;font-weight:600;font-size:15px">
              Zadaj pierwsze pytanie →
            </a>
          </td>
        </tr>

        <tr>
          <td style="background:#f8fafc;padding:20px 40px;border-top:1px solid #e2e8f0">
            <p style="margin:0;color:#94a3b8;font-size:12px;text-align:center;line-height:1.6">
              LexCorpus — 636 000 dokumentów prawnych w jednym miejscu<br>
              <a href="${BASE_URL}/regulamin" style="color:#94a3b8">Regulamin</a>
              &nbsp;·&nbsp;
              <a href="${BASE_URL}/polityka-prywatnosci" style="color:#94a3b8">Polityka prywatności</a>
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>`;

  const text = `Witaj w LexCorpus!\n\nTwoje konto jest gotowe. Zadaj pierwsze pytanie: ${BASE_URL}/ask\n\nPlan Free: 20 zapytań / dzień — bezpłatnie na zawsze.\n\nLexCorpus`;

  try {
    await sendMail({
      to:      email,
      subject: "Witaj w LexCorpus — Twoje konto jest gotowe ⚖️",
      html,
      text,
    });
  } catch (err) {
    // Non-blocking — don't fail registration if email fails
    console.error("[welcome-email] Failed:", err);
  }
}
