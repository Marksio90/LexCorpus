import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { spawn } from "node:child_process";

const MAX_SIZE_MB  = 10;
const ALLOWED_MIME = ["application/pdf", "text/plain",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document"];
const UPLOAD_DIR   = process.env.PRIVATE_DOCS_DIR ?? join(process.cwd(), "..", "data", "private");

/** GET /api/private-docs — lista dokumentów usera */
export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const docs = await prisma.privateDocument.findMany({
    where:   { userId: session.user.id },
    orderBy: { uploadedAt: "desc" },
    select:  { id: true, filename: true, sizeBytes: true, status: true,
               chunkCount: true, uploadedAt: true, processedAt: true, errorMsg: true },
  });
  return NextResponse.json(docs);
}

/** POST /api/private-docs — upload nowego dokumentu */
export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  // Tylko pro i kancelaria
  if (!["pro", "kancelaria"].includes(session.user.tier ?? "")) {
    return NextResponse.json({ error: "Prywatne dokumenty dostępne od planu Pro." }, { status: 403 });
  }

  const form = await req.formData();
  const file = form.get("file") as File | null;
  if (!file) return NextResponse.json({ error: "Brak pliku." }, { status: 400 });

  const sizeBytes = file.size;
  if (sizeBytes > MAX_SIZE_MB * 1024 * 1024) {
    return NextResponse.json({ error: `Maksymalny rozmiar pliku to ${MAX_SIZE_MB} MB.` }, { status: 400 });
  }
  if (!ALLOWED_MIME.includes(file.type) && !file.name.endsWith(".txt")) {
    return NextResponse.json({ error: "Obsługiwane formaty: PDF, TXT, DOCX." }, { status: 400 });
  }

  // Zapisz plik na dysk
  await mkdir(UPLOAD_DIR, { recursive: true });
  const doc = await prisma.privateDocument.create({
    data: {
      userId:   session.user.id,
      filename: file.name,
      mimeType: file.type || "text/plain",
      sizeBytes,
      status:   "processing",
    },
  });

  const tmpPath = join(UPLOAD_DIR, `${doc.id}_${file.name.replace(/[^a-z0-9._-]/gi, "_")}`);
  const buffer  = Buffer.from(await file.arrayBuffer());
  await writeFile(tmpPath, buffer);

  // Uruchom ingest_private.py asynchronicznie
  const dbPath = process.env.DATABASE_PATH ?? join(process.cwd(), "prisma", "dev.db");
  spawn(
    "python3",
    [
      "scripts/ingest_private.py",
      "--file",    tmpPath,
      "--user-id", session.user.id,
      "--doc-id",  doc.id,
      "--mime",    file.type || "text/plain",
      "--db",      dbPath,
      "--qdrant",  process.env.INTERNAL_API_URL || "http://api:8000",
    ],
    { detached: true, stdio: "ignore", cwd: join(process.cwd(), "..") }
  ).unref();

  return NextResponse.json({
    id:       doc.id,
    filename: doc.filename,
    status:   "processing",
  }, { status: 202 });
}
