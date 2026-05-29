import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import WidgetChat from "./WidgetChat";

export const dynamic = "force-dynamic";

export default async function WidgetPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const config = await prisma.widgetConfig.findUnique({ where: { token } });

  if (!config || !config.enabled) notFound();

  return (
    <WidgetChat
      token={token}
      title={config.title}
      welcomeMsg={config.welcomeMsg}
      accentColor={config.accentColor}
      logoUrl={config.logoUrl ?? null}
    />
  );
}
