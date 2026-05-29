import type { NextAuthOptions } from "next-auth";
import EmailProvider from "next-auth/providers/email";
import { PrismaAdapter } from "@auth/prisma-adapter";
import { prisma } from "@/lib/prisma";

const adminEmails = (process.env.ADMIN_EMAILS || "")
  .split(",")
  .map((e) => e.trim().toLowerCase())
  .filter(Boolean);

export const TIER_LIMITS: Record<string, number> = {
  free:       20,   // zapytań / dzień
  pro:        500,
  kancelaria: 9999,
};

export function isAdmin(email: string | null | undefined): boolean {
  if (!email) return false;
  if (adminEmails.length === 0) return false;
  return adminEmails.includes(email.toLowerCase());
}

export const authOptions: NextAuthOptions = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  adapter: PrismaAdapter(prisma) as any,

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
    async session({ session, user }) {
      if (session.user && user) {
        const dbUser = user as typeof user & { tier?: string; id?: string };
        session.user.id    = dbUser.id ?? "";
        session.user.tier  = dbUser.tier ?? "free";
        session.user.admin = isAdmin(user.email);
      }
      return session;
    },
  },

  pages: {
    signIn: "/login",
    error:  "/login",
  },

  session: { strategy: "database" },

  secret: (() => {
    const s = process.env.NEXTAUTH_SECRET;
    if (!s && process.env.NODE_ENV === "production") {
      throw new Error("NEXTAUTH_SECRET musi być ustawiony w produkcji");
    }
    return s ?? "dev-secret-change-in-production";
  })(),
};
