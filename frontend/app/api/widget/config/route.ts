import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { randomBytes } from "crypto";

function generateToken() {
  return randomBytes(20).toString("hex"); // 40-char hex token
}

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  if (session.user.tier !== "kancelaria") {
    return NextResponse.json({ error: "Widget dostępny tylko w planie Kancelaria." }, { status: 403 });
  }

  const config = await prisma.widgetConfig.findUnique({ where: { userId: session.user.id } });
  return NextResponse.json(config ?? null);
}

export async function POST() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  if (session.user.tier !== "kancelaria") {
    return NextResponse.json({ error: "Widget dostępny tylko w planie Kancelaria." }, { status: 403 });
  }

  const existing = await prisma.widgetConfig.findUnique({ where: { userId: session.user.id } });
  if (existing) return NextResponse.json(existing);

  const config = await prisma.widgetConfig.create({
    data: { userId: session.user.id, token: generateToken() },
  });
  return NextResponse.json(config, { status: 201 });
}

export async function PATCH(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return NextResponse.json({ error: "Nieautoryzowany." }, { status: 401 });

  if (session.user.tier !== "kancelaria") {
    return NextResponse.json({ error: "Widget dostępny tylko w planie Kancelaria." }, { status: 403 });
  }

  const body = await req.json() as {
    enabled?: boolean;
    title?: string;
    welcomeMsg?: string;
    accentColor?: string;
    logoUrl?: string | null;
    allowedDomains?: string;
  };

  const config = await prisma.widgetConfig.upsert({
    where:  { userId: session.user.id },
    create: { userId: session.user.id, token: generateToken(), ...body },
    update: body,
  });

  return NextResponse.json(config);
}
