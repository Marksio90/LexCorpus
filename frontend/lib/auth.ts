import type { NextAuthOptions } from "next-auth";
import EmailProvider from "next-auth/providers/email";

const adminEmails = (process.env.ADMIN_EMAILS || "")
  .split(",")
  .map((e) => e.trim().toLowerCase())
  .filter(Boolean);

export const authOptions: NextAuthOptions = {
  providers: [
    EmailProvider({
      server: {
        host: process.env.EMAIL_SERVER_HOST || "smtp.ethereal.email",
        port: Number(process.env.EMAIL_SERVER_PORT) || 587,
        auth: {
          user: process.env.EMAIL_SERVER_USER || "",
          pass: process.env.EMAIL_SERVER_PASSWORD || "",
        },
      },
      from: process.env.EMAIL_FROM || "noreply@lexcorpus.pl",
    }),
  ],
  callbacks: {
    async signIn({ user }) {
      if (adminEmails.length === 0) return true;
      return adminEmails.includes((user.email || "").toLowerCase());
    },
    async session({ session }) {
      return session;
    },
  },
  pages: {
    signIn: "/admin",
    error: "/admin",
  },
  secret: process.env.NEXTAUTH_SECRET || "dev-secret-change-in-production",
};
