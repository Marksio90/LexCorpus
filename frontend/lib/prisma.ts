import { PrismaClient } from "@prisma/client";
import { PrismaLibSQL } from "@prisma/adapter-libsql";
import { createClient } from "@libsql/client";
import path from "path";

function createPrismaClient() {
  const rawPath = process.env.DATABASE_PATH ?? path.join(process.cwd(), "prisma", "dev.db");
  // libsql expects file: prefix for local files
  const url = rawPath.startsWith("file:") ? rawPath : `file:${rawPath}`;
  const libsql  = createClient({ url });
  const adapter = new PrismaLibSQL(libsql);
  return new PrismaClient({
    adapter,
    log: process.env.NODE_ENV === "development" ? ["error"] : [],
  });
}

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma = globalForPrisma.prisma ?? createPrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
