import path from "node:path";
import { defineConfig } from "prisma/config";

const dbFile = process.env.DATABASE_PATH
  || path.join(process.cwd(), "prisma", "dev.db");

export default defineConfig({
  schema: "./prisma/schema.prisma",
  datasource: {
    url: `file:${dbFile}`,
  },
});
