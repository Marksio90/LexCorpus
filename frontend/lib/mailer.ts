import nodemailer from "nodemailer";

let _transport: nodemailer.Transporter | null = null;

function getTransport(): nodemailer.Transporter {
  if (_transport) return _transport;
  _transport = nodemailer.createTransport({
    host:   process.env.EMAIL_SERVER_HOST   || "smtp.ethereal.email",
    port:   Number(process.env.EMAIL_SERVER_PORT) || 587,
    secure: Number(process.env.EMAIL_SERVER_PORT) === 465,
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
  const from = process.env.EMAIL_FROM || "LexCorpus <noreply@lexcorpus.app>";
  await getTransport().sendMail({ from, ...opts });
}
