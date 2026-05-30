import { PrismaClient } from "@prisma/client";
import { PrismaPg } from "@prisma/adapter-pg";

function createPrismaClient() {
  // DATABASE_URL is required at runtime but may be absent during `next build`
  // static analysis. PrismaPg handles an empty string gracefully (no eager
  // connection is made until the first query).
  const adapter = new PrismaPg({
    connectionString: process.env.DATABASE_URL ?? "postgresql://localhost/placeholder",
  });
  return new PrismaClient({
    adapter,
    log: process.env.NODE_ENV === "development" ? ["error"] : [],
  });
}

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? createPrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
