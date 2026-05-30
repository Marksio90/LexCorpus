import nodemailer from "nodemailer";

const HOST = process.env.EMAIL_SERVER_HOST || "";
const PORT = Number(process.env.EMAIL_SERVER_PORT) || 587;
const IS_RESEND = HOST === "smtp.resend.com";

let _transport: nodemailer.Transporter | null = null;

function getTransport(): nodemailer.Transporter {
  if (_transport) return _transport;

  if (!HOST) {
    // Dev fallback: Ethereal (prints preview URL to console — no real delivery)
    _transport = nodemailer.createTransport({
      host: "smtp.ethereal.email",
      port: 587,
      auth: { user: "", pass: "" },
    });
    return _transport;
  }

  _transport = nodemailer.createTransport({
    host:       HOST,
    port:       PORT,
    secure:     PORT === 465,
    requireTLS: IS_RESEND,   // Resend rejects connections without STARTTLS
    auth: {
      user: process.env.EMAIL_SERVER_USER     || "",
      pass: process.env.EMAIL_SERVER_PASSWORD || "",
    },
  });
  return _transport;
}

export async function sendMail(opts: {
  to:      string;
  subject: string;
  html:    string;
  text?:   string;
}): Promise<void> {
  const from = process.env.EMAIL_FROM || "LexCorpus <noreply@lexcorpus.pl>";
  const info = await getTransport().sendMail({ from, ...opts });

  // Ethereal dev mode: print preview URL so you can see the email without real SMTP
  if (!HOST && info.messageId) {
    const { getTestMessageUrl } = await import("nodemailer");
    console.log("[mailer] DEV preview:", getTestMessageUrl(info));
  }
}
