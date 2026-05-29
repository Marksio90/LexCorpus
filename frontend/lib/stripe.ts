import Stripe from "stripe";

let _stripe: Stripe | null = null;

export function getStripe(): Stripe {
  if (!_stripe) _stripe = new Stripe(process.env.STRIPE_SECRET_KEY ?? "");
  return _stripe;
}

export const STRIPE_PRICES: Record<string, string> = {
  pro:        process.env.STRIPE_PRICE_PRO        ?? "",
  kancelaria: process.env.STRIPE_PRICE_KANCELARIA ?? "",
};

export const PLAN_META = {
  pro: {
    name:        "Pro",
    price:       "49 zł / mies.",
    description: "500 zapytań dziennie, priorytetowe wyniki, eksport PDF",
    color:       "blue",
  },
  kancelaria: {
    name:        "Kancelaria",
    price:       "299 zł / mies.",
    description: "Nieograniczone zapytania, dostęp API, 5 użytkowników, SLA",
    color:       "purple",
  },
} as const;
