export const dynamic = "force-dynamic";
import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";
import { stripe } from "@/lib/stripe";
import { prisma } from "@/lib/prisma";

// Mapa Stripe price ID → tier
function tierFromPriceId(priceId: string): string {
  if (priceId === (process.env.STRIPE_PRICE_PRO        ?? "")) return "pro";
  if (priceId === (process.env.STRIPE_PRICE_KANCELARIA ?? "")) return "kancelaria";
  return "free";
}

async function applySubscription(sub: Stripe.Subscription) {
  const userId = sub.metadata?.userId;
  if (!userId) return;

  const priceId = sub.items.data[0]?.price.id ?? "";
  const tier    = tierFromPriceId(priceId);
  const active  = sub.status === "active" || sub.status === "trialing";
  // current_period_end is available via items in newer Stripe API versions
  const periodEnd = (sub as unknown as Record<string, unknown>).current_period_end as number | undefined;
  const expires   = periodEnd ? new Date(periodEnd * 1000) : null;

  await prisma.user.update({
    where: { id: userId },
    data: {
      tier:                active ? tier : "free",
      tierExpiresAt:       expires,
      stripeSubscriptionId: sub.id,
      stripePriceId:       priceId,
    },
  });
}

export async function POST(req: NextRequest) {
  const body = await req.text();
  const sig  = req.headers.get("stripe-signature") ?? "";
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET ?? "";

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, sig, webhookSecret);
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Webhook error";
    return NextResponse.json({ error: msg }, { status: 400 });
  }

  switch (event.type) {
    case "checkout.session.completed": {
      const cs = event.data.object as Stripe.Checkout.Session;
      if (cs.mode === "subscription" && typeof cs.subscription === "string") {
        const sub = await stripe.subscriptions.retrieve(cs.subscription);
        // Backfill userId metadata from checkout if missing
        if (!sub.metadata?.userId && cs.metadata?.userId) {
          await stripe.subscriptions.update(cs.subscription, {
            metadata: { userId: cs.metadata.userId, plan: cs.metadata.plan ?? "" },
          });
          sub.metadata = cs.metadata;
        }
        await applySubscription(sub);
      }
      break;
    }

    case "customer.subscription.updated":
    case "customer.subscription.deleted": {
      const sub = event.data.object as Stripe.Subscription;
      await applySubscription(sub);
      break;
    }

    // Płatność nieudana — degradacja do free po grace period jest obsługiwana
    // przez subscription.updated ze status=past_due/canceled
    case "invoice.payment_failed":
      break;
  }

  return NextResponse.json({ received: true });
}
