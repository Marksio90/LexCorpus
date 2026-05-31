import type { NextAuthOptions } from "next-auth";
import EmailProvider from "next-auth/providers/email";
import CredentialsProvider from "next-auth/providers/credentials";
import { PrismaAdapter } from "@auth/prisma-adapter";
import { prisma } from "@/lib/prisma";
import { sendWelcomeEmail } from "@/lib/welcome-email";
import bcrypt from "bcryptjs";

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
    CredentialsProvider({
      name: "credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Hasło", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) {
          return null;
        }

        const user = await prisma.user.findUnique({
          where: { email: credentials.email.toLowerCase() },
        });

        if (!user || !user.password) {
          return null;
        }

        const isValid = await bcrypt.compare(
          credentials.password,
          user.password
        );

        if (!isValid) {
          return null;
        }

        return {
          id: user.id,
          email: user.email,
          name: user.name,
          image: user.image,
        };
      },
    }),
    EmailProvider({
      server: {
        host: process.env.EMAIL_SERVER_HOST || "smtp.ethereal.email",
        port: Number(process.env.EMAIL_SERVER_PORT) || 587,
        auth: {
          user: process.env.EMAIL_SERVER_USER || "",
          pass: process.env.EMAIL_SERVER_PASSWORD || "",
        },
      },
      from: process.env.EMAIL_FROM || "noreply@lexcorpus.app",
    }),
  ],

  callbacks: {
    async session({ session, user, token }) {
      // Dla CredentialsProvider user jest w token
      const userId = (user?.id || token?.sub || "") as string;
      if (session.user && userId) {
        const dbUser = await prisma.user.findUnique({
          where: { id: userId },
        });
        if (dbUser) {
          session.user.id = dbUser.id;
          session.user.tier = dbUser.tier ?? "free";
          session.user.admin = isAdmin(dbUser.email);
          session.user.onboardingCompletedAt = dbUser.onboardingCompletedAt ?? null;
        }
      }
      return session;
    },
    async jwt({ token, user }) {
      if (user) {
        token.sub = user.id;
      }
      return token;
    },
  },

  events: {
    async createUser({ user }) {
      if (user.email) {
        await sendWelcomeEmail(user.email);
      }
    },
  },

  pages: {
    signIn: "/login",
    error:  "/login",
  },

  session: { strategy: "jwt" },

  secret: (() => {
    const s = process.env.NEXTAUTH_SECRET;
    if (!s && process.env.NODE_ENV === "production") {
      throw new Error("NEXTAUTH_SECRET musi być ustawiony w produkcji");
    }
    return s ?? "dev-secret-change-in-production";
  })(),
};
